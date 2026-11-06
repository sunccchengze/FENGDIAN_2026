"""SequenceReplay copied from pitch 740d040; strict speed migration wraps it."""
import numpy as np
import torch
from .algorithm import ReplayBuffer

SOURCE_COMMIT = '740d04044e6b046dfe6256bfa3c2d4ef88925783'
SOURCE_FILE_SHA256 = '17badc54c0be33dfb97447c6c17eee448d8d3c2c788cf27b94e4561662f73590'
SOURCE_CLASS_SHA256 = '20196f46f83558be2b4ea8882fab02617f96f745a94fb8a9a59c9810ae682ecb'
TAIL_RULE = 'actual_m_bootstrap_unless_true_terminal_v1'


class SequenceReplay(ReplayBuffer):
    def __init__(self, config, n):
        super().__init__(config)
        if n not in (1, 8):
            raise ValueError('only frozen n=1/8 allowed')
        self.n, self.gamma = n, config.gamma
        self.sequence = np.full(self.capacity, -1, dtype=np.int64)
        self.insertions = 0
        self.m_histogram = np.zeros(n + 1, dtype=np.int64)
        self.last_indices = self.last_lengths = self.discounts = None

    @staticmethod
    def shared_done(value):
        a = np.asarray(value)
        if a.size not in (1, 3) or not np.isin(a, (0, 1)).all() or not (a == a.flat[0]).all():
            raise ValueError('one shared Boolean environment done required for all agents')
        return bool(a.flat[0])

    def add(self, obs, actions, rewards, next_obs, terminated):
        done = self.shared_done(terminated)
        slot = self.position
        super().add(obs, actions, rewards, next_obs, done)
        self.sequence[slot] = self.insertions
        self.insertions += 1

    def spans(self, indices):
        """Physical slots follow monotonically increasing insertion IDs, never array order alone."""
        slots = np.asarray(indices, dtype=int).copy()
        ends = slots.copy()
        lengths = np.ones(len(slots), dtype=np.int64)
        returns = self.data['rewards'][slots].copy()
        active = ~self.data['terminated'][slots, 0].astype(bool)
        for k in range(1, self.n):
            following = (ends + 1) % self.capacity
            available = active & (self.sequence[following] == self.sequence[ends] + 1)
            selected = np.flatnonzero(available)
            if not len(selected):
                break
            prev, nxt = ends[selected], following[selected]
            if not np.array_equal(self.data['next_obs'][prev], self.data['obs'][nxt]):
                raise ValueError('nonterminal replay continuity broken')
            remaining = self.data['obs'][nxt, :, 14]
            if not np.all(remaining < self.data['obs'][prev, :, 14]):
                raise ValueError('remaining episode time must decrease across each nonterminal edge')
            returns[selected] += (self.gamma ** k) * self.data['rewards'][nxt]
            ends[selected] = nxt
            lengths[selected] += 1
            active = available & ~self.data['terminated'][ends, 0].astype(bool)
        return returns, ends, lengths

    def sample(self, size, device):
        if size > self.size:
            raise ValueError('insufficient replay data')
        idx = self.rng.choice(self.size, size, replace=False)
        self.last_indices = idx.copy()
        if self.n == 1:
            self.last_lengths = np.ones(size, dtype=np.int64)
            result = {k: torch.as_tensor(v[idx], device=device) for k, v in self.data.items()}
        else:
            rewards, ends, self.last_lengths = self.spans(idx)
            result = {k: torch.as_tensor(v[ends if k in ('next_obs', 'terminated') else idx], device=device)
                      for k, v in self.data.items()}
            result['rewards'] = torch.as_tensor(rewards, device=device)
            self.discounts = torch.as_tensor(self.gamma ** self.last_lengths, dtype=torch.float32, device=device)[:, None]
        self.m_histogram += np.bincount(self.last_lengths, minlength=self.n + 1)
        return result

    def state_dict(self):
        return dict(super().state_dict(), sequence=self.sequence.copy(), insertions=self.insertions,
                    n=self.n, tail_rule=TAIL_RULE, m_histogram=self.m_histogram.copy())

    def load_state_dict(self, state):
        if 'n' in state and (state['n'] != self.n or state['tail_rule'] != TAIL_RULE):
            raise ValueError('return horizon/tail rule mismatch')
        super().load_state_dict(state)
        if 'sequence' in state:
            self.sequence[:] = state['sequence']
            self.insertions = state['insertions']
            self.m_histogram[:] = state['m_histogram']
        else:
            # Trusted legacy ring: position is next write, oldest if full.
            order = ((self.position + np.arange(self.size)) % self.capacity
                     if self.size == self.capacity else np.arange(self.size))
            self.sequence[order] = np.arange(self.size)
            self.insertions = self.size
        valid = self.sequence[self.sequence >= 0]
        if len(valid) != self.size or not np.array_equal(np.sort(valid), np.arange(self.insertions - self.size, self.insertions)):
            raise ValueError('invalid chronological replay IDs')
        if self.size < self.capacity and self.position != self.size:
            raise ValueError('invalid partial ring position')
