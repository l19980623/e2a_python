import numpy as np
from OMatch import OMatch
import Timer


class SLN:
    def __init__(self, mappings, events):
        self.p = None
        self.n = len(mappings)
        # Calculate ni values and the N value
        ni = [len(mappings[activity]) - 1 for activity in range(1, self.n + 1)]
        self.N = np.sum(ni)
        k = np.max(ni)
        # Make array 1-based
        ni.insert(0, 0)
        self.ni = ni

        self.w = np.zeros((self.n + 1, k + 1), np.float_)
        self.S = mappings
        self.E = events[:, 1]
        self.oMatch = OMatch(self.E, self.S, self.n, self.ni)
        self.M = self.oMatch.M

    def sln_1d(self, i, k):
        x = 0
        x_opt = 0
        self.w[i][k] = x
        f_opt, _ = self.f()
        p = self.p
        M = self.M
        done = False

        while not done:
            m = len(self.M)
            OPT = np.zeros((m,), np.int_)
            a = np.zeros((m,), np.int_)
            sigma = np.infty
            delta = np.zeros((m,), np.int_)

            for j in range(1, m):
                # M[j].w is variable (by default theta entries are all zeros)
                if M[j]['i'] == i and M[j]['k'] == k:
                    delta[j] = 1
                # Pre-store M[j].w for convenience
                j_weight = self.w[M[j]['i'], M[j]['k']]

                if j_weight + OPT[p[j]] > OPT[j - 1]:
                    OPT[j] = j_weight + OPT[p[j]]
                    a[j] = a[p[j]] + delta[j]
                    if a[p[j]] + delta[j] < a[j - 1]:
                        sigma = np.min([sigma, (j_weight + OPT[p[j]] - OPT[j - 1]) /
                                       (a[j - 1] - a[p[j]] - delta[j])])
                elif j_weight + OPT[p[j]] < OPT[j - 1]:
                    OPT[j] = OPT[j - 1]
                    a[j] = a[j - 1]
                    if a[p[j]] + delta[j] > a[j - 1]:
                        sigma = np.min([sigma, (j_weight + OPT[p[j]] - OPT[j - 1]) /
                                       (a[j - 1] - a[p[j]] - delta[j])])
                else:
                    if a[p[j]] + delta[j] <= a[j - 1]:
                        OPT[j] = OPT[j - 1]
                        a[j] = a[j - 1]
                    else:
                        OPT[j] = j_weight + OPT[p[j]]
                        a[j] = a[p[j]] + delta[j]

            if sigma == np.infty:
                sigma = 2
                done = True

            mu = x + sigma
            nu = x + sigma / 2
            self.w[i][k] = nu
            f_new, _ = self.f()
            if f_new < f_opt or (f_new == f_opt and nu == sigma / 2):
                x_opt = nu
                f_opt = f_new
            self.w[i][k] = mu
            f_new, _ = self.f()
            if f_new < f_opt:
                x_opt = mu
                f_opt = f_new
            if not done:
                x = mu

        return x_opt, f_opt

    def sln_nd(self, C):
        Timer.lap('ND SLN started')
        n = self.n
        ni = self.ni
        # Init the weights for S1s to C and the rest to 1
        for i in range(1, n + 1):
            self.w[i][1] = C
            for k in range(2, ni[i] + 1):
                self.w[i][k] = 1
        done = False
        f_opt, _ = self.f()
        Aw = []

        # Coordinate descent
        while not done:
            # Weight normalization
            W = 0
            for i in range(1, n + 1):
                for k in range(1, ni[i] + 1):
                    W += self.w[i][k]

            for i in range(1, n + 1):
                for k in range(1, ni[i] + 1):
                    self.w[i][k] = self.N * self.w[i][k] / W

            done = True

            # 1D minimization
            for i in range(1, n + 1):
                for k in range(1, ni[i] + 1):
                    Timer.lap(f'Optimizing SLN for i={i}, k={k}')
                    x_old = self.w[i][k]
                    x_new, _ = self.sln_1d(i, k)
                    f_new, Aw = self.f()

                    if f_new < f_opt:
                        done = False
                        self.w[i][k] = x_new
                        f_opt = f_new
                    else:
                        self.w[i][k] = x_old
        return self.w, Aw

    # Calculates the edit distance between two input sequences. This variant is also called
    # Levenshtein distance as insertions, deletions, and modifications on individual chars are
    # allowed (each with cost of 1)
    @staticmethod
    def calc_edit_distance(seq1, seq2):
        m = len(seq1)
        n = len(seq2)
        if m == 0:
            return n

        # dist[i,j] holds the Levenshtein distance between the first i chars of seq1 and first j chars of seq2
        dist = np.zeros((m, n), np.int_)

        # Prefixes of seq1 can be transformed to empty prefix of seq2 by removing all chars
        for i in range(1, m):
            dist[i][0] = i

        # Empty prefix of seq1 can be transformed to prefixes of seq2 by inserting every chars
        for j in range(1, n):
            dist[0][j] = j

        # Calculate the rest of the entries using DP
        for j in range(1, n):
            for i in range(1, m):
                if seq1[i] == seq2[j]:
                    sub_cost = 0
                else:
                    sub_cost = 1

                # Deletion, insertion, and substitution costs
                dist[i][j] = np.min([dist[i - 1][j] + 1,
                                     dist[i][j - 1] + 1,
                                     dist[i - 1][j - 1] + sub_cost])

        return dist[m - 1][n - 1]

    # Using given Mw, obtain a corresponding device event sequence and calculates the distance between the sequence and
    # given events
    def f(self):
        # Recalculate M using the updated weights
        Mw, self.p = self.oMatch.max_weight_sequence(self.w)
        m = len(Mw)
        Aw = np.full((m,), -1, np.int_)

        E1 = []
        # Assign Aw[j] to the corresponding i value
        if len(Mw) > 1:
            for j in range(1, m):
                Aw[j] = Mw[j]['i']
            for A in Aw[1:]:
                E1.extend(self.S[A][1][1:])

        return self.calc_edit_distance(E1, self.E[1:]), Aw
