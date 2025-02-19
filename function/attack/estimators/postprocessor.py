from __future__ import absolute_import, division, print_function, unicode_literals
from typing import List

import abc

import numpy as np


class Postprocessor(abc.ABC):
    """
    Abstract base class for postprocessing defences. Postprocessing defences are not included in the loss function
    evaluation for loss gradients or the calculation of class gradients.
    """

    params: List[str] = []

    def __init__(self, is_fitted: bool = False, apply_fit: bool = True, apply_predict: bool = True) -> None:
        """
        Create a postprocessing object.

        Optionally, set attributes.
        """
        self._is_fitted = bool(is_fitted)
        self._apply_fit = bool(apply_fit)
        self._apply_predict = bool(apply_predict)
        Postprocessor._check_params(self)

    @property
    def is_fitted(self) -> bool:
        """
        Return the state of the postprocessing object.

        :return: `True` if the postprocessing model has been fitted (if this applies).
        """
        return self._is_fitted

    @property
    def apply_fit(self) -> bool:
        """
        Property of the defence indicating if it should be applied at training time.

        :return: `True` if the defence should be applied when fitting a model, `False` otherwise.
        """
        return self._apply_fit

    @property
    def apply_predict(self) -> bool:
        """
        Property of the defence indicating if it should be applied at test time.

        :return: `True` if the defence should be applied at prediction time, `False` otherwise.
        """
        return self._apply_predict

    @abc.abstractmethod
    def __call__(self, preds: np.ndarray) -> np.ndarray:
        """
        Perform model postprocessing and return postprocessed output.

        :param preds: model output to be postprocessed.
        :return: Postprocessed model output.
        """
        raise NotImplementedError

    def fit(self, preds: np.ndarray, **kwargs) -> None:
        """
        Fit the parameters of the postprocessor if it has any.

        :param preds: Training set to fit the postprocessor.
        :param kwargs: Other parameters.
        """
        pass

    def set_params(self, **kwargs) -> None:
        """
        Take in a dictionary of parameters and apply checks before saving them as attributes.
        """
        for key, value in kwargs.items():
            if key in self.params:
                setattr(self, key, value)
        self._check_params()

    def _check_params(self) -> None:
        pass