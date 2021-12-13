import warnings
import numpy as np
import pytransform3d.rotations as pr
from ._base import DMPBase
from ._forcing_term import ForcingTerm
from ._canonical_system import canonical_system_alpha
from ._dmp import dmp_step_rk4, dmp_open_loop, dmp_imitate, ridge_regression


class CartesianDMP(DMPBase):
    """Cartesian dynamical movement primitive.

    The Cartesian DMP handles orientation and position separately. The
    orientation is represented by a quaternion. The quaternion DMP is
    implemented according to

    A. Ude, B. Nemec, T. Petric, J. Murimoto:
    Orientation in Cartesian space dynamic movement primitives (2014),
    IEEE International Conference on Robotics and Automation (ICRA),
    pp. 2997-3004, doi: 10.1109/ICRA.2014.6907291,
    https://ieeexplore.ieee.org/document/6907291

    While the dimension of the state space is 7, the dimension of the
    velocity, acceleration, and forcing term is 6.

    Parameters
    ----------
    execution_time : float
        Execution time of the DMP.

    dt : float, optional (default: 0.01)
        Time difference between DMP steps.

    n_weights_per_dim : int, optional (default: 10)
        Number of weights of the function approximator per dimension.

    int_dt : float, optional (default: 0.001)
        Time difference for Euler integration.

    Attributes
    ----------
    dt_ : float
        Time difference between DMP steps. This value can be changed to adapt
        the frequency.
    """
    def __init__(
            self, execution_time, dt=0.01, n_weights_per_dim=10, int_dt=0.001):
        super(CartesianDMP, self).__init__(7, 6)
        self.execution_time = execution_time
        self.dt_ = dt
        self.n_weights_per_dim = n_weights_per_dim
        self.int_dt = int_dt
        alpha_z = canonical_system_alpha(
            0.01, self.execution_time, 0.0, self.int_dt)
        self.forcing_term_pos = ForcingTerm(
            3, self.n_weights_per_dim, self.execution_time, 0.0, 0.8,
            alpha_z)
        self.forcing_term_rot = ForcingTerm(
            3, self.n_weights_per_dim, self.execution_time, 0.0, 0.8,
            alpha_z)

        self.alpha_y = 25.0
        self.beta_y = self.alpha_y / 4.0

    def step(self, last_y, last_yd, coupling_term=None):
        """DMP step.

        Parameters
        ----------
        last_y : array, shape (7,)
            Last state.

        last_yd : array, shape (6,)
            Last time derivative of state (velocity).

        coupling_term : object, optional (default: None)
            Coupling term that will be added to velocity.

        Returns
        -------
        y : array, shape (14,)
            Next state.

        yd : array, shape (12,)
            Next time derivative of state (velocity).
        """
        assert len(last_y) == 7
        assert len(last_yd) == 6

        self.last_t = self.t
        self.t += self.dt_

        # TODO tracking error

        self.current_y[:], self.current_yd[:] = last_y, last_yd
        dmp_step_rk4(
            self.last_t, self.t,
            self.current_y[:3], self.current_yd[:3],
            self.goal_y[:3], self.goal_yd[:3], self.goal_ydd[:3],
            self.start_y[:3], self.start_yd[:3], self.start_ydd[:3],
            self.execution_time, 0.0,
            self.alpha_y, self.beta_y,
            self.forcing_term_pos,
            coupling_term=coupling_term,
            int_dt=self.int_dt)
        dmp_step_quaternion(
            self.last_t, self.t,
            self.current_y[3:], self.current_yd[3:],
            self.goal_y[3:], self.goal_yd[3:], self.goal_ydd[3:],
            self.start_y[3:], self.start_yd[3:], self.start_ydd[3:],
            self.execution_time, 0.0,
            self.alpha_y, self.beta_y,
            self.forcing_term_rot,
            coupling_term=coupling_term,
            int_dt=self.int_dt)
        return np.copy(self.current_y), np.copy(self.current_yd)

    def open_loop(self, run_t=None, coupling_term=None):
        """Run DMP open loop.

        Parameters
        ----------
        run_t : float, optional (default: execution_time)
            Run time of DMP. Can be shorter or longer than execution_time.

        coupling_term : object, optional (default: None)
            Coupling term that will be added to velocity.

        Returns
        -------
        T : array, shape (n_steps,)
            Time for each step.

        Y : array, shape (n_steps, 7)
            State at each step.
        """
        T, Yp = dmp_open_loop(
                self.execution_time, 0.0, self.dt_,
                self.start_y[:3], self.goal_y[:3],
                self.alpha_y, self.beta_y,
                self.forcing_term_pos,
                coupling_term,
                run_t, self.int_dt)
        _, Yr = dmp_open_loop_quaternion(
                self.execution_time, 0.0, self.dt_,
                self.start_y[3:], self.goal_y[3:],
                self.alpha_y, self.beta_y,
                self.forcing_term_rot,
                coupling_term,
                run_t, self.int_dt)
        return T, np.hstack((Yp, Yr))

    def imitate(self, T, Y, regularization_coefficient=0.0,
                allow_final_velocity=False):
        """Imitate demonstration.

        Parameters
        ----------
        T : array, shape (n_steps,)
            Time for each step.

        Y : array, shape (n_steps, 7)
            State at each step.

        regularization_coefficient : float, optional (default: 0)
            Regularization coefficient for regression.

        allow_final_velocity : bool, optional (default: False)
            Allow a final velocity.
        """
        self.forcing_term_pos.weights[:, :] = dmp_imitate(
            T, Y[:, :3],
            n_weights_per_dim=self.n_weights_per_dim,
            regularization_coefficient=regularization_coefficient,
            alpha_y=self.alpha_y, beta_y=self.beta_y,
            overlap=self.forcing_term_pos.overlap,
            alpha_z=self.forcing_term_pos.alpha_z,
            allow_final_velocity=allow_final_velocity)[0]
        self.forcing_term_rot.weights[:, :] = dmp_quaternion_imitation(
            T, Y[:, 3:],
            n_weights_per_dim=self.n_weights_per_dim,
            regularization_coefficient=regularization_coefficient,
            alpha_y=self.alpha_y, beta_y=self.beta_y,
            overlap=self.forcing_term_rot.overlap,
            alpha_z=self.forcing_term_rot.alpha_z,
            allow_final_velocity=allow_final_velocity)[0]

        self.configure(start_y=Y[0], goal_y=Y[-1])

    def get_weights(self):
        """Get weight vector of DMP.

        Returns
        -------
        weights : array, shape (6 * n_weights_per_dim,)
            Current weights of the DMP.
        """
        return np.concatenate((self.forcing_term_pos.weights.ravel(),
                               self.forcing_term_rot.weights.ravel()))

    def set_weights(self, weights):
        """Set weight vector of DMP.

        Parameters
        ----------
        weights : array, shape (6 * n_weights_per_dim,)
            New weights of the DMP.
        """
        n_pos_weights = self.forcing_term_pos.weights.size
        self.forcing_term_pos.weights[:, :] = weights[:n_pos_weights].reshape(
            -1, self.n_weights_per_dim)
        self.forcing_term_rot.weights[:, :] = weights[n_pos_weights:].reshape(
            -1, self.n_weights_per_dim)


def dmp_step_quaternion_python(
        last_t, t,
        current_y, current_yd,
        goal_y, goal_yd, goal_ydd,
        start_y, start_yd, start_ydd,
        goal_t, start_t, alpha_y, beta_y,
        forcing_term,
        coupling_term=None,
        coupling_term_precomputed=None,
        int_dt=0.001):
    """Integrate quaternion DMP for one step with Euler integration."""
    if start_t >= goal_t:
        raise ValueError("Goal must be chronologically after start!")

    if t <= start_t:
        return np.copy(start_y), np.copy(start_yd), np.copy(start_ydd)

    execution_time = goal_t - start_t

    current_ydd = np.empty_like(current_yd)

    current_t = last_t
    while current_t < t:
        dt = int_dt
        if t - current_t < int_dt:
            dt = t - current_t
        current_t += dt

        if coupling_term is not None:
            cd, cdd = coupling_term.coupling(current_y, current_yd)
        else:
            cd, cdd = np.zeros(3), np.zeros(3)
        if coupling_term_precomputed is not None:
            cd += coupling_term_precomputed[0]
            cdd += coupling_term_precomputed[1]

        f = forcing_term(current_t).squeeze()

        current_ydd[:] = (
            alpha_y * (beta_y * pr.compact_axis_angle_from_quaternion(
                           pr.concatenate_quaternions(
                               goal_y, pr.q_conj(current_y)))
                       - execution_time * current_yd)
            + f + cdd) / execution_time ** 2
        current_yd += dt * current_ydd + cd / execution_time
        current_y[:] = pr.concatenate_quaternions(
            pr.quaternion_from_compact_axis_angle(dt * current_yd), current_y)


try:
    from dmp_fast import dmp_step_quaternion
except ImportError:
    warnings.warn(
        "Could not import fast quaternion DMP. "
        "Build Cython extension if you want it.",
        UserWarning)
    dmp_step_quaternion = dmp_step_quaternion_python


def dmp_quaternion_imitation(
        T, Y, n_weights_per_dim, regularization_coefficient, alpha_y, beta_y,
        overlap, alpha_z, allow_final_velocity):
    """Compute weights and metaparameters of quaternion DMP.

    Parameters
    ----------
    T : array, shape (n_steps,)
        Time of each step.

    Y : array, shape (n_steps, 4)
        Orientation at each step.

    n_weights_per_dim : int
        Number of weights per dimension.

    regularization_coefficient : float, optional (default: 0)
        Regularization coefficient for regression.

    alpha_y : float
        Parameter of the transformation system.

    beta_y : float
        Parameter of the transformation system.

    overlap : float
        At which value should radial basis functions of the forcing term
        overlap?

    alpha_z : float
        Parameter of the canonical system.

    allow_final_velocity : bool
        Whether a final velocity is allowed. Will be set to 0 otherwise.

    Returns
    -------
    weights : array, shape (3, n_weights_per_dim)
        Weights of the forcing term.

    start_y : array, shape (4,)
        Start orientation.

    start_yd : array, shape (3,)
        Start velocity.

    start_ydd : array, shape (3,)
        Start acceleration.

    goal_y : array, shape (4,)
        Final orientation.

    goal_yd : array, shape (3,)
        Final velocity.

    goal_ydd : array, shape (3,)
        Final acceleration.
    """
    # https://github.com/rock-learning/bolero/blob/master/src/representation/dmp/implementation/src/Dmp.cpp#L702
    if regularization_coefficient < 0.0:
        raise ValueError("Regularization coefficient must be >= 0!")

    forcing_term = ForcingTerm(
        3, n_weights_per_dim, T[-1], T[0], overlap, alpha_z)
    F, start_y, start_yd, start_ydd, goal_y, goal_yd, goal_ydd = \
        determine_forces_quaternion(T, Y, alpha_y, beta_y,
                                    allow_final_velocity)  # n_steps x n_dims

    X = forcing_term.design_matrix(T)  # n_weights_per_dim x n_steps

    return (ridge_regression(X, F, regularization_coefficient),
            start_y, start_yd, start_ydd, goal_y, goal_yd, goal_ydd)


def determine_forces_quaternion(T, Y, alpha_y, beta_y, allow_final_velocity):
    """Determine forces that the forcing term should generate.

    Parameters
    ----------
    T : array, shape (n_steps,)
        Time of each step.

    Y : array, shape (n_steps, n_dims)
        Position at each step.

    alpha_y : float
        Parameter of the transformation system.

    beta_y : float
        Parameter of the transformation system.

    allow_final_velocity : bool
        Whether a final velocity is allowed. Will be set to 0 otherwise.

    Returns
    -------
    F : array, shape (n_steps, n_dims)
        Forces.

    start_y : array, shape (4,)
        Start orientation.

    start_yd : array, shape (3,)
        Start velocity.

    start_ydd : array, shape (3,)
        Start acceleration.

    goal_y : array, shape (4,)
        Final orientation.

    goal_yd : array, shape (3,)
        Final velocity.

    goal_ydd : array, shape (3,)
        Final acceleration.
    """
    # https://github.com/rock-learning/bolero/blob/master/src/representation/dmp/implementation/src/Dmp.cpp#L670
    n_dims = 3

    DT = np.gradient(T)

    Yd = pr.quaternion_gradient(Y) / DT[:, np.newaxis]
    if not allow_final_velocity:
        Yd[-1, :] = 0.0

    Ydd = np.empty_like(Yd)
    for d in range(n_dims):
        Ydd[:, d] = np.gradient(Yd[:, d]) / DT
    Ydd[-1, :] = 0.0

    execution_time = T[-1] - T[0]
    goal_y = Y[-1]
    F = np.empty((len(T), n_dims))
    for t in range(len(T)):
        F[t, :] = (
            execution_time ** 2 * Ydd[t]
            - alpha_y * (beta_y * pr.compact_axis_angle_from_quaternion(
                             pr.concatenate_quaternions(
                                 goal_y, pr.q_conj(Y[t])))
                         - Yd[t] * execution_time))
    return F, Y[0], Yd[0], Ydd[0], Y[-1], Yd[-1], Ydd[-1]


def dmp_open_loop_quaternion(
        goal_t, start_t, dt, start_y, goal_y, alpha_y, beta_y, forcing_term,
        coupling_term=None, run_t=None, int_dt=0.001):
    t = start_t
    y = np.copy(start_y)
    yd = np.zeros(3)
    T = [start_t]
    Y = [np.copy(y)]
    if run_t is None:
        run_t = goal_t
    while t < run_t:
        last_t = t
        t += dt
        dmp_step_quaternion(
            last_t, t, y, yd,
            goal_y=goal_y, goal_yd=np.zeros_like(yd),
            goal_ydd=np.zeros_like(yd),
            start_y=start_y, start_yd=np.zeros_like(yd),
            start_ydd=np.zeros_like(yd),
            goal_t=goal_t, start_t=start_t, alpha_y=alpha_y, beta_y=beta_y,
            forcing_term=forcing_term, coupling_term=coupling_term,
            int_dt=int_dt)
        T.append(t)
        Y.append(np.copy(y))
    return np.asarray(T), np.asarray(Y)
