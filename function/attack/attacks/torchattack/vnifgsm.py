import torch
import torch.nn as nn
import numpy as np
from typing import Optional
from function.attack.attacks.attack import EvasionAttack


class VNIFGSM(EvasionAttack):
    r"""
    VNI-FGSM in the paper 'Enhancing the Transferability of Adversarial Attacks through Variance Tuning
    [https://arxiv.org/abs/2103.15571], Published as a conference paper at CVPR 2021
    Modified from "https://github.com/JHL-HUST/VT"

    Distance Measure : Linf

    Arguments:
        classifier 
        eps (float): maximum perturbation. (Default: 8/255)
        alpha (float): step size. (Default: 2/255)
        steps (int): number of iterations. (Default: 10)
        decay (float): momentum factor. (Default: 1.0)
        N (int): the number of sampled examples in the neighborhood. (Default: 5)
        beta (float): the upper bound of neighborhood. (Default: 3/2)

    Shape:
        - x: :math:`(N, C, H, W)` where `N = number of batches`, `C = number of channels`,        `H = height` and `W = width`. It must have a range [0, 1].
        - y: :math:`(N)` where each value :math:`y_i` is :math:`0 \leq y_i \leq` `number of labels`.
        - output: :math:`(N, C, H, W)`.

    Examples::
        >>> attack = VNIFGSM(classifier, eps=8/255, alpha=2/255, steps=10, decay=1.0, N=5, beta=3/2)
        >>> adv_images = attack.generate(x, y)

    """

    def __init__(self, classifier, eps=8/255, alpha=2/255, steps=10, decay=1.0, N=5, beta=3/2):
        self.eps = eps
        self.steps = steps
        self.decay = decay
        self.alpha = alpha
        self.N = N
        self.beta = beta
        self.classifier = classifier
        self.device = classifier.device

    def generate(self, x : np.ndarray, y : Optional[np.ndarray] = None):
        r"""
        Overridden.
        """
        if y is None:
            y = self.classifier.predict(x)

        if len(y.shape) == 2:
            y = self.classifier.reduce_labels(y)

        images = torch.from_numpy(x).to(self.device)
        labels = torch.from_numpy(y).to(self.device)

        # if self.targeted:
        #     target_labels = self.get_target_label(images, labels)

        momentum = torch.zeros_like(images).detach().to(self.device)
        v = torch.zeros_like(images).detach().to(self.device)
        adv_images = images.clone().detach()

        for _ in range(self.steps):
            adv_images.requires_grad = True
            nes_images = adv_images + self.decay * self.alpha * momentum
            outputs = self.classifier._model(nes_images)

            # Calculate loss
            # if self.targeted:
            #     cost = -loss(outputs, target_labels)
            # else:
            cost = self.classifier._loss(outputs[-1], labels.long())

            # Update adversarial images
            adv_grad = torch.autograd.grad(cost, adv_images,
                                           retain_graph=False, create_graph=False)[0]

            grad = (adv_grad + v) / torch.mean(torch.abs(adv_grad + v),
                                               dim=(1, 2, 3), keepdim=True)
            grad = grad + momentum * self.decay
            momentum = grad

            # Calculate Gradient Variance
            GV_grad = torch.zeros_like(images).detach().to(self.device)
            for _ in range(self.N):
                neighbor_images = adv_images.detach() + \
                    torch.randn_like(images).uniform_(-self.eps *
                                                      self.beta, self.eps*self.beta)
                neighbor_images.requires_grad = True
                outputs = self.classifier._model(neighbor_images)

                # Calculate loss
                # if self.targeted:
                #     cost = -loss(outputs, target_labels)
                # else:
                cost = self.classifier._loss(outputs[-1], labels.long())
                GV_grad += torch.autograd.grad(cost, neighbor_images,
                                               retain_graph=False, create_graph=False)[0]
            # obtaining the gradient variance
            v = GV_grad / self.N - adv_grad

            adv_images = adv_images.detach() + self.alpha*grad.sign()
            delta = torch.clamp(adv_images - images,
                                min=-self.eps, max=self.eps)
            adv_images = torch.clamp(images + delta, min=0, max=1).detach()

        adv_images = adv_images.cpu().numpy()
        return adv_images
