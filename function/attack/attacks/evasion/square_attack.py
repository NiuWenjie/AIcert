from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import bisect
import random
from typing import Optional, Union, Callable, TYPE_CHECKING
import numpy as np
from tqdm.auto import trange
from function.attack.attacks.config import MY_NUMPY_DTYPE
from function.attack.attacks.attack import EvasionAttack
from function.attack.estimators.estimator import BaseEstimator, NeuralNetworkMixin
if TYPE_CHECKING:
    from function.attack.attacks.utils import CLASSIFIER_TYPE
import torch
import time
import math
import torch.nn.functional as F

class SquareAttack(EvasionAttack):
    attack_params = EvasionAttack.attack_params + [
        "norm",
        "n_queries",
        "eps",
        "p_init",
        "loss_type",
        "n_restarts",
        "targeted",
        "batch_size",
    ]

    _estimator_requirements = (BaseEstimator, NeuralNetworkMixin)

    def __init__(
        self,
        estimator: "CLASSIFIER_TYPE",
        norm='inf',
        n_queries=5,
        eps=8/255,
        p_init=0.05,
        loss_type='margin', # "ce"
        n_restarts=1,
        targeted=False,
        batch_size=128,
    ):

        super().__init__(estimator=estimator)
        self.n_queries = n_queries
        self.eps = eps
        self.p_init = p_init
        self.n_restarts = n_restarts
        self.seed = None
        self.targeted = targeted
        self.loss = loss_type
        self.rescale_schedule = True
        self.batch_size = batch_size
    
    def margin_and_loss(self, x, y):
        logits = torch.from_numpy(self.estimator.predict(x.cpu().detach().numpy())).to(self.estimator.device)
        xent = F.cross_entropy(logits, y, reduction='none')
        u = torch.arange(x.shape[0])
        y_corr = logits[u, y].clone()
        logits[u, y] = -float('inf')
        y_others = logits.max(dim=-1)[0]

        if not self.targeted:
            if self.loss == 'ce':
                return y_corr - y_others, -1. * xent
            elif self.loss == 'margin':
                return y_corr - y_others, y_corr - y_others
        else:
            return y_others - y_corr, xent

    def random_target_classes(self, y_pred, n_classes):
        y = torch.zeros_like(y_pred)
        for counter in range(y_pred.shape[0]):
            l = list(range(n_classes))
            l.remove(y_pred[counter])
            t = self.random_int(0, len(l))
            y[counter] = l[t]

        return y.long().to(self.estimator.device)

    def check_shape(self, x):
        return x if len(x.shape) == (self.ndims + 1) else x.unsqueeze(0)

    def random_choice(self, shape):
        t = 2 * torch.rand(shape).to(self.estimator.device) - 1
        return torch.sign(t)

    def random_int(self, low=0, high=1, shape=[1]):
        t = low + (high - low) * torch.rand(shape).to(self.estimator.device)
        return t.long()

    def normalize(self, x):
        if self.norm == 'Linf':
            t = x.abs().view(x.shape[0], -1).max(1)[0]
            return x / (t.view(-1, *([1] * self.ndims)) + 1e-12)

        elif self.norm == 'L2':
            t = (x ** 2).view(x.shape[0], -1).sum(-1).sqrt()
            return x / (t.view(-1, *([1] * self.ndims)) + 1e-12)
        
        elif self.norm == 'L1':
            t = x.abs().view(x.shape[0], -1).sum(dim=-1)
            return x / (t.view(-1, *([1] * self.ndims)) + 1e-12)
    
    def lp_norm(self, x):
        if self.norm == 'L2':
            t = (x ** 2).view(x.shape[0], -1).sum(-1).sqrt()
            return t.view(-1, *([1] * self.ndims))
        
        elif self.norm == 'L1':
            t = x.abs().view(x.shape[0], -1).sum(dim=-1)
            return t.view(-1, *([1] * self.ndims))
    
    def eta_rectangles(self, x, y):
        delta = torch.zeros([x, y]).to(self.estimator.device)
        x_c, y_c = x // 2 + 1, y // 2 + 1

        counter2 = [x_c - 1, y_c - 1]
        if self.norm == 'L2':
            for counter in range(0, max(x_c, y_c)):
              delta[max(counter2[0], 0):min(counter2[0] + (2*counter + 1), x),
                  max(0, counter2[1]):min(counter2[1] + (2*counter + 1), y)
                  ] += 1.0/(torch.Tensor([counter + 1]).view(1, 1).to(
                  self.estimator.device) ** 2)
              counter2[0] -= 1
              counter2[1] -= 1
            delta /= (delta ** 2).sum(dim=(0, 1), keepdim=True).sqrt()

        elif self.norm == 'L1':
            for counter in range(0, max(x_c, y_c)):
              delta[max(counter2[0], 0):min(counter2[0] + (2*counter + 1), x),
                  max(0, counter2[1]):min(counter2[1] + (2*counter + 1), y)
                  ] += 1.0/(torch.Tensor([counter + 1]).view(1, 1).to(
                  self.estimator.device) ** 4)
              counter2[0] -= 1
              counter2[1] -= 1
            delta /= delta.abs().sum(dim=(), keepdim=True)
        
        return delta

    def eta(self, s):
        if self.norm == 'L2':
            delta = torch.zeros([s, s]).to(self.estimator.device)
            delta[:s // 2] = self.eta_rectangles(s // 2, s)
            delta[s // 2:] = -1. * self.eta_rectangles(s - s // 2, s)
            delta /= (delta ** 2).sum(dim=(0, 1), keepdim=True).sqrt()

        elif self.norm == 'L1':
            delta = torch.zeros([s, s]).to(self.estimator.device)
            delta[:s // 2] = self.eta_rectangles(s // 2, s)
            delta[s // 2:] = -1. * self.eta_rectangles(s - s // 2, s)
            #delta = self.eta_rectangles(s, s)
            delta /= delta.abs().sum(dim=(), keepdim=True)
        
        if torch.rand([1]) > 0.5:
            delta = delta.permute([1, 0])

        return delta

    def p_selection(self, it):
        if self.rescale_schedule:
            it = int(it / self.n_queries * 10000)
        if 10 < it <= 50:
            p = self.p_init / 2
        elif 50 < it <= 200:
            p = self.p_init / 4
        elif 200 < it <= 500:
            p = self.p_init / 8
        elif 500 < it <= 1000:
            p = self.p_init / 16
        elif 1000 < it <= 2000:
            p = self.p_init / 32
        elif 2000 < it <= 4000:
            p = self.p_init / 64
        elif 4000 < it <= 6000:
            p = self.p_init / 128
        elif 6000 < it <= 8000:
            p = self.p_init / 256
        elif 8000 < it:
            p = self.p_init / 512
        else:
            p = self.p_init

        return p

    def attack_single_run(self, x, y):
        if self.norm == 1:
            self.norm = "L1"
        elif self.norm == 2:
            self.norm = "L2"
        elif self.norm in ["inf", np.inf]:
            self.norm = "Linf"

        def L1_projection(x2, y2, eps1):
            x = x2.clone().float().view(x2.shape[0], -1)
            y = y2.clone().float().view(y2.shape[0], -1)
            sigma = y.clone().sign()
            u = torch.min(1 - x - y, x + y)
            u = torch.min(torch.zeros_like(y), u)
            l = -torch.clone(y).abs()
            d = u.clone()
            bs, indbs = torch.sort(-torch.cat((u, l), 1), dim=1)
            bs2 = torch.cat((bs[:, 1:], torch.zeros(bs.shape[0], 1).to(bs.device)), 1)
            inu = 2*(indbs < u.shape[1]).float() - 1
            size1 = inu.cumsum(dim=1)
            s1 = -u.sum(dim=1)
            
            c = eps1 - y.clone().abs().sum(dim=1)
            c5 = s1 + c < 0
            c2 = c5.nonzero().squeeze(1)
            
            s = s1.unsqueeze(-1) + torch.cumsum((bs2 - bs) * size1, dim=1)
            
            if c2.nelement != 0:            
                lb = torch.zeros_like(c2).float()
                ub = torch.ones_like(lb) *(bs.shape[1] - 1)
            
                #print(c2.shape, lb.shape)
                
                nitermax = torch.ceil(torch.log2(torch.tensor(bs.shape[1]).float()))
                counter2 = torch.zeros_like(lb).long()
                counter = 0
                    
                while counter < nitermax:
                    counter4 = torch.floor((lb + ub) / 2.)
                    counter2 = counter4.type(torch.LongTensor)
                    
                    c8 = s[c2, counter2] + c[c2] < 0
                    ind3 = c8.nonzero().squeeze(1)
                    ind32 = (~c8).nonzero().squeeze(1)
                    #print(ind3.shape)
                    if ind3.nelement != 0:
                        lb[ind3] = counter4[ind3]
                    if ind32.nelement != 0:
                        ub[ind32] = counter4[ind32]
                    
                    #print(lb, ub)
                    counter += 1
                
                lb2 = lb.long()
                alpha = (-s[c2, lb2] -c[c2]) / size1[c2, lb2 + 1] + bs2[c2, lb2]
                d[c2] = -torch.min(torch.max(-u[c2], alpha.unsqueeze(-1)), -l[c2])
            
            return (sigma * d).view(x2.shape)

        with torch.no_grad():
            # adv = x.clone()
            c, h, w = x.shape[1:]
            n_features = c * h * w
            n_ex_total = x.shape[0]

            if self.norm == 'Linf':
                x_best = torch.clamp(x + self.eps * self.random_choice(
                    [x.shape[0], c, 1, w]), 0., 1.)
                margin_min, loss_min = self.margin_and_loss(x_best, y)
                n_queries = torch.ones(x.shape[0]).to(self.estimator.device)
                s_init = int(math.sqrt(self.p_init * n_features / c))
                
                if (margin_min < 0.0).all():
                    return n_queries, x_best
                
                for i_iter in range(self.n_queries):
                    idx_to_fool = (margin_min > 0.0).nonzero().squeeze()
                    
                    x_curr = self.check_shape(x[idx_to_fool])
                    x_best_curr = self.check_shape(x_best[idx_to_fool])
                    y_curr = y[idx_to_fool]
                    if len(y_curr.shape) == 0:
                        y_curr = y_curr.unsqueeze(0)
                    margin_min_curr = margin_min[idx_to_fool]
                    loss_min_curr = loss_min[idx_to_fool]
                    
                    p = self.p_selection(i_iter)
                    s = max(int(round(math.sqrt(p * n_features / c))), 1)
                    s = min(s, min(h, w))
                    vh = self.random_int(0, h - s)
                    vw = self.random_int(0, w - s)
                    new_deltas = torch.zeros([c, h, w]).to(self.estimator.device)
                    new_deltas[:, vh:vh + s, vw:vw + s
                        ] = 2. * self.eps * self.random_choice([c, 1, 1])
                    
                    x_new = x_best_curr + new_deltas
                    x_new = torch.min(torch.max(x_new, x_curr - self.eps),
                        x_curr + self.eps)
                    x_new = torch.clamp(x_new, 0., 1.)
                    x_new = self.check_shape(x_new)
                    
                    margin, loss = self.margin_and_loss(x_new, y_curr)

                    # update loss if new loss is better
                    idx_improved = (loss < loss_min_curr).float()

                    loss_min[idx_to_fool] = idx_improved * loss + (
                        1. - idx_improved) * loss_min_curr

                    # update margin and x_best if new loss is better
                    # or misclassification
                    idx_miscl = (margin <= 0.).float()
                    idx_improved = torch.max(idx_improved, idx_miscl)

                    margin_min[idx_to_fool] = idx_improved * margin + (
                        1. - idx_improved) * margin_min_curr
                    idx_improved = idx_improved.reshape([-1,
                        *[1]*len(x.shape[:-1])])
                    x_best[idx_to_fool] = idx_improved * x_new + (
                        1. - idx_improved) * x_best_curr
                    n_queries[idx_to_fool] += 1.

                    ind_succ = (margin_min <= 0.).nonzero().squeeze()

                    if ind_succ.numel() == n_ex_total:
                        break
              
            elif self.norm == 'L2':
                delta_init = torch.zeros_like(x)
                s = h // 5
                sp_init = (h - s * 5) // 2
                vh = sp_init + 0
                for _ in range(h // s):
                    vw = sp_init + 0
                    for _ in range(w // s):
                        delta_init[:, :, vh:vh + s, vw:vw + s] += self.eta(
                            s).view(1, 1, s, s) * self.random_choice(
                            [x.shape[0], c, 1, 1])
                        vw += s
                    vh += s

                x_best = torch.clamp(x + self.normalize(delta_init
                    ) * self.eps, 0., 1.)
                margin_min, loss_min = self.margin_and_loss(x_best, y)
                n_queries = torch.ones(x.shape[0]).to(self.estimator.device)
                s_init = int(math.sqrt(self.p_init * n_features / c))
                
                if (margin_min < 0.0).all():
                    return n_queries, x_best

                for i_iter in range(self.n_queries):
                    idx_to_fool = (margin_min > 0.0).nonzero().squeeze()

                    x_curr = self.check_shape(x[idx_to_fool])
                    x_best_curr = self.check_shape(x_best[idx_to_fool])
                    y_curr = y[idx_to_fool]
                    if len(y_curr.shape) == 0:
                        y_curr = y_curr.unsqueeze(0)
                    margin_min_curr = margin_min[idx_to_fool]
                    loss_min_curr = loss_min[idx_to_fool]

                    delta_curr = x_best_curr - x_curr
                    p = self.p_selection(i_iter)
                    s = max(int(round(math.sqrt(p * n_features / c))), 3)
                    if s % 2 == 0:
                        s += 1
                    s = min(s, min(h, w))

                    vh = self.random_int(0, h - s)
                    vw = self.random_int(0, w - s)
                    new_deltas_mask = torch.zeros_like(x_curr)
                    new_deltas_mask[:, :, vh:vh + s, vw:vw + s] = 1.0
                    norms_window_1 = (delta_curr[:, :, vh:vh + s, vw:vw + s
                        ] ** 2).sum(dim=(-2, -1), keepdim=True).sqrt()

                    vh2 = self.random_int(0, h - s)
                    vw2 = self.random_int(0, w - s)
                    new_deltas_mask_2 = torch.zeros_like(x_curr)
                    new_deltas_mask_2[:, :, vh2:vh2 + s, vw2:vw2 + s] = 1.

                    norms_image = self.lp_norm(x_best_curr - x_curr)
                    mask_image = torch.max(new_deltas_mask, new_deltas_mask_2)
                    norms_windows = ((delta_curr * mask_image) ** 2).sum(dim=(
                        -2, -1), keepdim=True).sqrt()

                    new_deltas = torch.ones([x_curr.shape[0], c, s, s]
                        ).to(self.estimator.device)
                    new_deltas *= (self.eta(s).view(1, 1, s, s) *
                        self.random_choice([x_curr.shape[0], c, 1, 1]))
                    old_deltas = delta_curr[:, :, vh:vh + s, vw:vw + s] / (
                        1e-12 + norms_window_1)
                    new_deltas += old_deltas
                    new_deltas = new_deltas / (1e-12 + (new_deltas ** 2).sum(
                        dim=(-2, -1), keepdim=True).sqrt()) * (torch.max(
                        (self.eps * torch.ones_like(new_deltas)) ** 2 -
                        norms_image ** 2, torch.zeros_like(new_deltas)) /
                        c + norms_windows ** 2).sqrt()
                    delta_curr[:, :, vh2:vh2 + s, vw2:vw2 + s] = 0.
                    delta_curr[:, :, vh:vh + s, vw:vw + s] = new_deltas + 0

                    x_new = torch.clamp(x_curr + self.normalize(delta_curr
                        ) * self.eps, 0. ,1.)
                    x_new = self.check_shape(x_new)
                    norms_image = self.lp_norm(x_new - x_curr)

                    margin, loss = self.margin_and_loss(x_new, y_curr)

                    # update loss if new loss is better
                    idx_improved = (loss < loss_min_curr).float()

                    loss_min[idx_to_fool] = idx_improved * loss + (
                        1. - idx_improved) * loss_min_curr

                    # update margin and x_best if new loss is better
                    # or misclassification
                    idx_miscl = (margin <= 0.).float()
                    idx_improved = torch.max(idx_improved, idx_miscl)

                    margin_min[idx_to_fool] = idx_improved * margin + (
                        1. - idx_improved) * margin_min_curr
                    idx_improved = idx_improved.reshape([-1,
                        *[1]*len(x.shape[:-1])])
                    x_best[idx_to_fool] = idx_improved * x_new + (
                        1. - idx_improved) * x_best_curr
                    n_queries[idx_to_fool] += 1.

                    ind_succ = (margin_min <= 0.).nonzero().squeeze()

                    assert (x_new != x_new).sum() == 0
                    assert (x_best != x_best).sum() == 0
                    
                    if ind_succ.numel() == n_ex_total:
                        break
            
            elif self.norm == 'L1':
                delta_init = torch.zeros_like(x)
                s = h // 5
                sp_init = (h - s * 5) // 2
                vh = sp_init + 0
                for _ in range(h // s):
                    vw = sp_init + 0
                    for _ in range(w // s):
                        delta_init[:, :, vh:vh + s, vw:vw + s] += self.eta(
                            s).view(1, 1, s, s) * self.random_choice(
                            [x.shape[0], c, 1, 1])
                        vw += s
                    vh += s

                #x_best = torch.clamp(x + self.normalize(delta_init
                #    ) * self.eps, 0., 1.)
                r_best = L1_projection(x, delta_init, self.eps * (1. - 1e-6))
                x_best = x + delta_init + r_best
                margin_min, loss_min = self.margin_and_loss(x_best, y)
                n_queries = torch.ones(x.shape[0]).to(self.estimator.device)
                s_init = int(math.sqrt(self.p_init * n_features / c))
                
                if (margin_min < 0.0).all():
                    return n_queries, x_best

                for i_iter in range(self.n_queries):
                    idx_to_fool = (margin_min > 0.0).nonzero().squeeze()

                    x_curr = self.check_shape(x[idx_to_fool])
                    x_best_curr = self.check_shape(x_best[idx_to_fool])
                    y_curr = y[idx_to_fool]
                    if len(y_curr.shape) == 0:
                        y_curr = y_curr.unsqueeze(0)
                    margin_min_curr = margin_min[idx_to_fool]
                    loss_min_curr = loss_min[idx_to_fool]

                    delta_curr = x_best_curr - x_curr
                    p = self.p_selection(i_iter)
                    s = max(int(round(math.sqrt(p * n_features / c))), 3)
                    if s % 2 == 0:
                        s += 1
                        #pass
                    s = min(s, min(h, w))
                    
                    vh = self.random_int(0, h - s)
                    vw = self.random_int(0, w - s)
                    new_deltas_mask = torch.zeros_like(x_curr)
                    new_deltas_mask[:, :, vh:vh + s, vw:vw + s] = 1.0
                    norms_window_1 = delta_curr[:, :, vh:vh + s, vw:vw + s
                        ].abs().sum(dim=(-2, -1), keepdim=True)

                    vh2 = self.random_int(0, h - s)
                    vw2 = self.random_int(0, w - s)
                    new_deltas_mask_2 = torch.zeros_like(x_curr)
                    new_deltas_mask_2[:, :, vh2:vh2 + s, vw2:vw2 + s] = 1.

                    norms_image = self.lp_norm(x_best_curr - x_curr)
                    mask_image = torch.max(new_deltas_mask, new_deltas_mask_2)
                    norms_windows = (delta_curr * mask_image).abs().sum(dim=(
                        -2, -1), keepdim=True)

                    new_deltas = torch.ones([x_curr.shape[0], c, s, s]
                        ).to(self.estimator.device)
                    new_deltas *= (self.eta(s).view(1, 1, s, s) *
                        self.random_choice([x_curr.shape[0], c, 1, 1]))
                    old_deltas = delta_curr[:, :, vh:vh + s, vw:vw + s] / (
                        1e-12 + norms_window_1)
                    new_deltas += old_deltas
                    new_deltas = new_deltas / (1e-12 + new_deltas.abs().sum(
                        dim=(-2, -1), keepdim=True)) * (torch.max(
                        self.eps * torch.ones_like(norms_image) -
                        norms_image, torch.zeros_like(norms_image)) /
                        c + norms_windows) * c
                    delta_curr[:, :, vh2:vh2 + s, vw2:vw2 + s] = 0.
                    delta_curr[:, :, vh:vh + s, vw:vw + s] = new_deltas + 0

                    #
                    #norms_image_old = self.lp_norm(delta_curr)
                    r_curr = L1_projection(x_curr, delta_curr, self.eps * (1. - 1e-6))
                    x_new = x_curr + delta_curr + r_curr
                    x_new = self.check_shape(x_new)
                    norms_image = self.lp_norm(x_new - x_curr)

                    margin, loss = self.margin_and_loss(x_new, y_curr)

                    # update loss if new loss is better
                    idx_improved = (loss < loss_min_curr).float()

                    loss_min[idx_to_fool] = idx_improved * loss + (
                        1. - idx_improved) * loss_min_curr

                    # update margin and x_best if new loss is better
                    # or misclassification
                    idx_miscl = (margin <= 0.).float()
                    idx_improved = torch.max(idx_improved, idx_miscl)

                    margin_min[idx_to_fool] = idx_improved * margin + (
                        1. - idx_improved) * margin_min_curr
                    idx_improved = idx_improved.reshape([-1,
                        *[1]*len(x.shape[:-1])])
                    x_best[idx_to_fool] = idx_improved * x_new + (
                        1. - idx_improved) * x_best_curr
                    n_queries[idx_to_fool] += 1.

                    ind_succ = (margin_min <= 0.).nonzero().squeeze()
                    
                    assert (x_new != x_new).sum() == 0
                    assert (x_best != x_best).sum() == 0
        
                    if ind_succ.numel() == n_ex_total:
                        break
        return n_queries, x_best

    def generate(self, x, y=None):
        self.orig_dim = list(x.shape[1:])
        self.ndims = len(self.orig_dim)

        adv_x = x.copy()
        for batch_id in trange(
            int(np.ceil(x.shape[0] / float(self.batch_size))), desc="Square Attack"
        ):
            batch_index_1, batch_index_2 = batch_id * self.batch_size, (batch_id + 1) * self.batch_size
            x_batch = x[batch_index_1:batch_index_2].copy()

            if y != None and y.any() != None:
                y_batch = torch.tensor(np.argmax(y[batch_index_1:batch_index_2], axis=1)).to(self.estimator.device)
            else:
                if not self.targeted:
                    with torch.no_grad():
                        output = torch.from_numpy(self.estimator.predict(x_batch)).to(self.estimator.device)
                        y_pred = output.max(1)[1]
                        y_batch = y_pred.clone().to(self.estimator.device)
                else:
                    with torch.no_grad():
                        output = torch.from_numpy(self.estimator.predict(x_batch)).to(self.estimator.device)
                        n_classes = output.shape[-1]
                        y_pred = output.max(1)[1]
                        y_batch = self.random_target_classes(y_pred, n_classes)
            
            if not self.targeted:
                acc = torch.from_numpy(self.estimator.predict(x_batch)).to(self.estimator.device).max(1)[1] == y_batch
            else:
                acc = torch.from_numpy(self.estimator.predict(x_batch)).to(self.estimator.device).max(1)[1] != y_batch

            if self.seed is None:
                self.seed = time.time()
            torch.random.manual_seed(self.seed)
            torch.cuda.random.manual_seed(self.seed)

            for _ in range(self.n_restarts):
                ind_to_fool = acc.nonzero().squeeze().cpu()
                if len(ind_to_fool.shape) == 0:
                    ind_to_fool = ind_to_fool.unsqueeze(0)
                if ind_to_fool.numel() != 0:
                    x_to_fool = torch.tensor(x_batch)[ind_to_fool].clone().to(self.estimator.device)
                    y_to_fool = y_batch[ind_to_fool].clone()

                    _, adv_curr = self.attack_single_run(x_to_fool, y_to_fool)

                    output_curr = torch.from_numpy(self.estimator.predict(adv_curr.cpu().detach().numpy())).to(self.estimator.device)
                    if not self.targeted:
                        acc_curr = output_curr.max(1)[1] == y_to_fool
                    else:
                        acc_curr = output_curr.max(1)[1] != y_to_fool
                    ind_curr = (acc_curr == 0).nonzero().squeeze().cpu()

                    acc[ind_to_fool[ind_curr]] = 0
                    adv_x[ind_to_fool[ind_curr].cpu().numpy()+batch_index_1] = adv_curr.cpu().detach().numpy()[ind_curr.cpu().numpy()]
        return adv_x.astype(MY_NUMPY_DTYPE)