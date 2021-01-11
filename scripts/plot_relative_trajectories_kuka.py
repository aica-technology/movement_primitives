import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mocap.pandas_utils import match_columns, rename_stream_groups
from mocap.conversion import array_from_dataframe
from movement_primitives.dmp import DualCartesianDMP


def load_data(path):
    trajectory = pd.read_csv(path, sep=" ")
    patterns = ["time\.microseconds",
                "kuka_lbr_cart_pos_ctrl_left\.current_feedback\.pose\.position\.data.*",
                "kuka_lbr_cart_pos_ctrl_left\.current_feedback\.pose\.orientation\.re.*",
                "kuka_lbr_cart_pos_ctrl_left\.current_feedback\.pose\.orientation\.im.*",
                "kuka_lbr_cart_pos_ctrl_right\.current_feedback\.pose\.position\.data.*",
                "kuka_lbr_cart_pos_ctrl_right\.current_feedback\.pose\.orientation\.re.*",
                "kuka_lbr_cart_pos_ctrl_right\.current_feedback\.pose\.orientation\.im.*"]
    columns = match_columns(trajectory, patterns)
    trajectory = trajectory[columns]
    group_rename = {
        "(time\.microseconds)": "Time",
        "(kuka_lbr_cart_pos_ctrl_left\.current_feedback\.pose\.position\.data).*": "left_pose",
        "(kuka_lbr_cart_pos_ctrl_left\.current_feedback\.pose\.orientation).*": "left_pose",
        "(kuka_lbr_cart_pos_ctrl_right\.current_feedback\.pose\.position\.data).*": "right_pose",
        "(kuka_lbr_cart_pos_ctrl_right\.current_feedback\.pose\.orientation).*": "right_pose"
    }
    trajectory = rename_stream_groups(trajectory, group_rename)
    trajectory["Time"] = trajectory["Time"] / 1e6
    trajectory["Time"] -= trajectory["Time"].iloc[0]
    T = trajectory["Time"].to_numpy()
    P = array_from_dataframe(
        trajectory,
        ["left_pose[0]", "left_pose[1]", "left_pose[2]",
        "left_pose.re", "left_pose.im[0]", "left_pose.im[1]", "left_pose.im[2]",
        "right_pose[0]", "right_pose[1]", "right_pose[2]",
        "right_pose.re", "right_pose.im[0]", "right_pose.im[1]", "right_pose.im[2]"])
    return T, P


n_weights_per_dim = 10

#pattern = "data/kuka/20200129_peg_in_hole/csv_processed/01_peg_in_hole_both_arms/*.csv"
#pattern = "data/kuka/20191213_carry_heavy_load/csv_processed/01_heavy_load_no_tilt_0cm_dual_arm/*.csv"
pattern = "data/kuka/20191023_rotate_panel_varying_size/csv_processed/panel_450mm_counterclockwise/*.csv"

all_T = []
all_P = []
all_weights = []
all_starts = []
all_goals = []
all_execution_times = []

for idx, path in enumerate(list(glob.glob(pattern))):
    print("Loading %s" % path)
    T, P = load_data(path)

    execution_time = T[-1]
    dt = np.mean(np.diff(T))
    if dt < 0.005:  # HACK
        continue
    dmp = DualCartesianDMP(
        execution_time=execution_time, dt=dt,
        n_weights_per_dim=n_weights_per_dim, int_dt=0.01, k_tracking_error=0.0)
    dmp.imitate(T, P)
    weights = dmp.get_weights()

    all_T.append(T)
    all_P.append(P)

    all_weights.append(weights)
    all_starts.append(P[0])
    all_goals.append(P[-1])
    all_execution_times.append(execution_time)



all_parameters = np.vstack([
    np.hstack((w, s, g, e)) for w, s, g, e in zip(
        all_weights, all_starts, all_goals, all_execution_times)])
mean_parameters = np.mean(all_parameters, axis=0)
cov_parameters = np.cov(all_parameters, rowvar=False)

all_T = np.asarray(all_T)
all_P = np.asarray(all_P)

plt.figure()
axes = [plt.subplot(2, 3, d) for d in range(1, 7)]

for T, P in zip(all_T, all_P):
    dP = P[:, :3] - P[:, 7:10]
    axes[0].plot(T, dP[:, 0], color="k", alpha=0.3)
    axes[1].plot(T, dP[:, 1], color="k", alpha=0.3)
    axes[2].plot(T, dP[:, 2], color="k", alpha=0.3)

# next trajectories are sampled from Gaussian DMP
random_state = np.random.RandomState(0)
for idx in range(5):
    print("Reproduce #%d" % (idx + 1))

    params = random_state.multivariate_normal(mean_parameters, cov_parameters)
    n_weights = 2 * 6 * n_weights_per_dim
    weights = params[:n_weights]
    start = params[n_weights:n_weights + 14]
    goal = params[n_weights + 14:n_weights + 2 * 14]
    execution_time = params[-1]

    dmp = DualCartesianDMP(
        execution_time=execution_time, dt=0.01,
        n_weights_per_dim=n_weights_per_dim, int_dt=0.01)
    dmp.set_weights(weights)
    dmp.configure(start_y=start, goal_y=goal)
    T, P = dmp.open_loop(run_t=execution_time)

    axes[3].plot(T, P[:, 0] - P[:, 7], color="k")
    axes[4].plot(T, P[:, 1] - P[:, 8], color="k")
    axes[5].plot(T, P[:, 2] - P[:, 9], color="k")

for d in range(3):
    ylim = axes[d].get_ylim()
    axes[d].set_ylim((ylim[0] - 0.05, ylim[1] + 0.05))
    axes[3 + d].set_ylim((ylim[0] - 0.05, ylim[1] + 0.05))

plt.show()