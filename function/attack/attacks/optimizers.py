import numpy as np

class Adam:
    """
    A simple implementation of Adam optimizer.
    """

    def __init__(self, alpha=0.001, beta_1=0.9, beta_2=0.999, epsilon=1e-8):
        self.m_dx = 0.0
        self.v_dx = 0.0
        self.beta_1 = beta_1
        self.beta_2 = beta_2
        self.epsilon = epsilon
        self.alpha = alpha

    def update(self, niter: int, x: np.ndarray, delta_x: np.ndarray) -> np.ndarray:
        """
        Update one iteration.

        :param niter: Number of current iteration.
        :param x: Current value.
        :param delta_x: Current first derivative at `x`.
        :return: Updated value.
        """
        # momentum
        self.m_dx = self.beta_1 * self.m_dx + (1 - self.beta_1) * delta_x

        # rms
        self.v_dx = self.beta_2 * self.v_dx + (1 - self.beta_2) * (delta_x ** 2)

        # bias
        m_dw_corr = self.m_dx / (1 - self.beta_1 ** niter)
        v_dw_corr = self.v_dx / (1 - self.beta_2 ** niter)

        # update
        x = x - self.alpha * (m_dw_corr / (np.sqrt(v_dw_corr) + self.epsilon))

        return x

    def optimize(self, func, jac, x_0, max_iter, loss_converged):
        """
        Optimize function for max. iterations.

        :param func: A callable returning the function value.
        :param jac: A callable returning the Jacobian value.
        :param x_0: Initial value.
        :param max_iter: Number of optimisation iterations.
        :param loss_converged: Target loss.
        :return: Optimized value.
        """

        num_iter = 1
        converged = False

        while not converged and num_iter <= max_iter:

            delta_x = jac(x_0)

            x_0 = self.update(num_iter, x=x_0, delta_x=delta_x)

            loss = func(x_0)

            if loss < loss_converged:
                converged = True

            num_iter += 1

        return x_0
