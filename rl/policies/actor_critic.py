from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from gym import spaces

from rl.policies.distributions import FixedCategorical, FixedNormal, \
    MixedDistribution, FixedGumbelSoftmax
from rl.policies.utils import MLP
from util.pytorch import to_tensor


class Actor(nn.Module):
    def __init__(self, config, ob_space, ac_space, tanh_policy, deterministic=False):
        super().__init__()
        self._config = config
        self._activation_fn = getattr(F, config.activation)
        self._tanh = tanh_policy
        self._deterministic= deterministic

    @property
    def info(self):
        return {}

    def act(self, ob, is_train=True, return_log_prob=False):
        ob = to_tensor(ob, self._config.device)
        means, stds = self.forward(ob, self._deterministic)

        dists = OrderedDict()
        for k, space in self._ac_space.spaces.items():
            if isinstance(space, spaces.Box):
                if self._deterministic:
                    stds[k] = torch.zeros_like(means[k])
                dists[k] = FixedNormal(means[k], stds[k])
            else:
                if self._config.meta_algo == 'sac' or self._config.algo == 'sac':
                    dists[k] = FixedGumbelSoftmax(torch.tensor(self._config.temperature), logits=means[k])
                else:
                    dists[k] = FixedCategorical(logits=means[k])

        actions = OrderedDict()
        mixed_dist = MixedDistribution(dists)
        if not is_train or self._deterministic:
            activations = mixed_dist.mode()
        else:
            activations = mixed_dist.sample()


        if return_log_prob:
            log_probs = mixed_dist.log_probs(activations)

        for k, space in self._ac_space.spaces.items():
            z = activations[k]
            if self._tanh and isinstance(space, spaces.Box):
                # action_scale = to_tensor((self._ac_space[k].high), self._config.device).detach()
                # action = torch.tanh(z) * action_scale
                action = torch.tanh(z)
                if return_log_prob:
                    # follow the Appendix C. Enforcing Action Bounds
                    # log_det_jacobian = 2 * (np.log(2.) - z - F.softplus(-2. * z)).sum(dim=1, keepdim=True)
                    log_det_jacobian = 2 * (np.log(2.) - z - F.softplus(-2. * z)).sum(dim=-1, keepdim=True)
                    # log_det_jacobian = torch.log((1-torch.tanh(z).pow(2))+1e-6).sum(dim=1, keepdim=True)
                    log_probs[k] = log_probs[k] - log_det_jacobian
            else:
                action = z
            if action.shape[0] == 1:
                actions[k] = action.detach().cpu().numpy().squeeze(0)
            else:
                actions[k] = action.detach().cpu().numpy()

        if return_log_prob:
            log_probs_ = torch.cat(list(log_probs.values()), -1).sum(-1, keepdim=True)
            # if log_probs_.min() < -100:
            #     print('sampling an action with a probability of 1e-100')
            #     import ipdb; ipdb.set_trace()

            log_probs_ = log_probs_.detach().cpu().numpy().squeeze(0)
            return actions, activations, log_probs_
        else:
            return actions, activations

    def act_log(self, ob, activations=None):
        means, stds = self.forward(ob)

        dists = OrderedDict()
        actions = OrderedDict()
        for k, space in self._ac_space.spaces.items():
            if isinstance(space, spaces.Box):
                if self._deterministic:
                    stds[k] = torch.zeros_like(means[k])
                dists[k] = FixedNormal(means[k], stds[k])
            else:
                if self._config.meta_algo == 'sac' or self._config.algo == 'sac':
                    dists[k] = FixedGumbelSoftmax(torch.tensor(self._config.temperature), logits=means[k])
                else:
                    dists[k] = FixedCategorical(logits=means[k])

        mixed_dist = MixedDistribution(dists)


        activations_ = mixed_dist.rsample() if activations is None else activations
        for k in activations_.keys():
            if len(activations_[k].shape) == 1:
                activations_[k] = activations_[k].unsqueeze(0)
        log_probs = mixed_dist.log_probs(activations_)

        for k, space in self._ac_space.spaces.items():
            z = activations_[k]
            if self._tanh and isinstance(space, spaces.Box):
                # action_scale = to_tensor((self._ac_space[k].high), self._config.device).detach()
                action = torch.tanh(z)
                # action = torch.tanh(z)
                # follow the Appendix C. Enforcing Action Bounds
                # log_det_jacobian = 2 * (np.log(2.) - z - F.softplus(-2. * z)).sum(dim=1, keepdim=True)
                log_det_jacobian = 2 * (np.log(2.) - z - F.softplus(-2. * z)).sum(dim=-1, keepdim=True)
                log_probs[k] = log_probs[k] - log_det_jacobian
            else:
                action = z
                log_probs[k] *= self._config.discrete_ent_coef

            actions[k] = action

        log_probs_ = torch.cat(list(log_probs.values()), -1).sum(-1, keepdim=True)
        # if log_probs_.min() < -100:
        #     print(ob)
        #     print(log_probs_.min())
        #     import ipdb; ipdb.set_trace()
        if activations is None:
            return actions, log_probs_
        else:
            ents = mixed_dist.entropy()
            return log_probs_, ents

    def act_log_debug(self, ob, activations=None):
        means, stds = self.forward(ob)

        dists = OrderedDict()
        actions = OrderedDict()
        for k, space in self._ac_space.spaces.items():
            if isinstance(space, spaces.Box):
                dists[k] = FixedNormal(means[k], stds[k])
            else:
                dists[k] = FixedCategorical(logits=means[k])

        mixed_dist = MixedDistribution(dists)

        activations_ = mixed_dist.rsample() if activations is None else activations
        log_probs = mixed_dist.log_probs(activations_)

        for k, space in self._ac_space.spaces.items():
            z = activations_[k]
            if self._tanh and isinstance(space, spaces.Box):
                action = torch.tanh(z) * to_tensor((self._ac_space[k].high), self._config.device)
                # follow the Appendix C. Enforcing Action Bounds
                log_det_jacobian = 2 * (np.log(2.) - z - F.softplus(-2. * z)).sum(dim=-1, keepdim=True)
                log_probs[k] = log_probs[k] - log_det_jacobian
            else:
                action = z

            actions[k] = action

        ents = mixed_dist.entropy()
        #print(torch.cat(list(log_probs.values()), -1))
        log_probs_ = torch.cat(list(log_probs.values()), -1).sum(-1, keepdim=True)
        if log_probs_.min() < -100:
            print(ob)
            print(log_probs_.min())
            import ipdb; ipdb.set_trace()
        if activations is None:
            return actions, log_probs_
        else:
            return log_probs_, ents, log_probs, means, stds


class Critic(nn.Module):
    def __init__(self, config):
        super().__init__()
        self._config = config

