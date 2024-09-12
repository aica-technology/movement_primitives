import numpy as np


def ensure_1d_array(value, n_dims, var_name):
    """Process scalar or array-like input to ensure it is a 1D numpy array.

    Parameters
    ----------
    value : float or array-like, shape (n_dims,)
        Argument to be processed.

    n_dims : int
        Expected length of the 1d array.

    var_name : str
        Name of the variable in case an exception has to be raised.

    Returns
    -------
    value : array, shape (n_dims,)
        1D numpy array with dtype float.

    Raises
    ------
    ValueError
        If the argument is not compatible.
    """
    value = np.atleast_1d(value).astype(float)
    if value.ndim == 1 and value.shape[0] == 1:
        value = np.repeat(value, n_dims)
    if value.ndim > 1 or value.shape[0] != n_dims:
        raise ValueError(
            f"{var_name} has incorrect shape, expected ({n_dims},) "
            f"got {value.shape}")
    return value
