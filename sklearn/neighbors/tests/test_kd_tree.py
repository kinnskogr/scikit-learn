import numpy as np
from numpy.testing import assert_allclose
from sklearn.neighbors.kd_tree import (KDTree, NeighborsHeap,
                                       simultaneous_sort, kernel_norm,
                                       nodeheap_sort, DTYPE, ITYPE)
from sklearn.neighbors.dist_metrics import DistanceMetric
from sklearn.utils.testing import SkipTest

V = np.random.random((3, 3))
V = np.dot(V, V.T)

DIMENSION = 3

METRICS = {'euclidean':{},
           'manhattan':{},
           'chebyshev':{},
           'minkowski':dict(p=3)}


def brute_force_neighbors(X, Y, k, metric, **kwargs):
    D = DistanceMetric.get_metric(metric, **kwargs).pairwise(Y, X)
    ind = np.argsort(D, axis=1)[:, :k]
    dist = D[np.arange(Y.shape[0])[:, None], ind]
    return dist, ind


def test_kd_tree_query():
    np.random.seed(0)
    X = np.random.random((40, DIMENSION))
    Y = np.random.random((10, DIMENSION))

    def check_neighbors(dualtree, breadth_first, k, metric, kwargs):
        kdt = KDTree(X, leaf_size=1, metric=metric, **kwargs)
        dist1, ind1 = kdt.query(Y, k, dualtree=dualtree,
                               breadth_first=breadth_first)
        dist2, ind2 = brute_force_neighbors(X, Y, k, metric, **kwargs)

        # don't check indices here: if there are any duplicate distances,
        # the indices may not match.  Distances should not have this problem.
        assert_allclose(dist1, dist2)

    for (metric, kwargs) in METRICS.iteritems():
        for k in (1, 3, 5):
            for dualtree in (True, False):
                for breadth_first in (True, False):
                    yield (check_neighbors,
                           dualtree, breadth_first,
                           k, metric, kwargs)


def test_kd_tree_query_radius(n_samples=100, n_features=10):
    np.random.seed(0)
    X = 2 * np.random.random(size=(n_samples, n_features)) - 1
    query_pt = np.zeros(n_features, dtype=float)

    eps = 1E-15  # roundoff error can cause test to fail
    kdt = KDTree(X, leaf_size=5)
    rad = np.sqrt(((X - query_pt) ** 2).sum(1))

    for r in np.linspace(rad[0], rad[-1], 100):
        ind = kdt.query_radius(query_pt, r + eps)[0]
        i = np.where(rad <= r + eps)[0]

        ind.sort()
        i.sort()

        assert_allclose(i, ind)


def test_kd_tree_query_radius_distance(n_samples=100, n_features=10):
    np.random.seed(0)
    X = 2 * np.random.random(size=(n_samples, n_features)) - 1
    query_pt = np.zeros(n_features, dtype=float)

    eps = 1E-15  # roundoff error can cause test to fail
    kdt = KDTree(X, leaf_size=5)
    rad = np.sqrt(((X - query_pt) ** 2).sum(1))

    for r in np.linspace(rad[0], rad[-1], 100):
        ind, dist = kdt.query_radius(query_pt, r + eps, return_distance=True)

        ind = ind[0]
        dist = dist[0]

        d = np.sqrt(((query_pt - X[ind]) ** 2).sum(1))

        assert_allclose(d, dist)


def compute_kernel_slow(Y, X, kernel, h):
    d = np.sqrt(((Y[:, None, :] - X) ** 2).sum(-1))
    norm = kernel_norm(h, X.shape[1], kernel)

    if kernel == 'gaussian':
        return norm * np.exp(-0.5 * (d * d) / (h * h)).sum(-1)
    elif kernel == 'tophat':
        return norm * (d < h).sum(-1)
    elif kernel == 'epanechnikov':
        return norm * ((1.0 - (d * d) / (h * h)) * (d < h)).sum(-1)
    elif kernel == 'exponential':
        return norm * (np.exp(-d / h)).sum(-1)
    elif kernel == 'linear':
        return norm * ((1 - d / h) * (d < h)).sum(-1)
    elif kernel == 'cosine':
        return norm * (np.cos(0.5 * np.pi * d / h) * (d < h)).sum(-1)
    else:
        raise ValueError('kernel not recognized')
    

def test_kd_tree_KDE(n_samples=100, n_features=3):
    np.random.seed(0)
    X = np.random.random((n_samples, n_features))
    Y = np.random.random((n_samples, n_features))
    kdt = KDTree(X, leaf_size=10)

    for kernel in ['gaussian', 'tophat', 'epanechnikov',
                   'exponential', 'linear', 'cosine']:
        for h in [0.01, 0.1, 1]:
            dens_true = compute_kernel_slow(Y, X, kernel, h)
            def check_results(kernel, h, atol, rtol, breadth_first):
                dens = kdt.kernel_density(Y, h, atol=atol, rtol=rtol,
                                         kernel=kernel,
                                         breadth_first=breadth_first)
                assert_allclose(dens, dens_true, atol=atol,
                                rtol=max(1E-7, rtol))

            for rtol in [0, 1E-5]:
                for atol in [1E-6, 1E-2]:
                    for breadth_first in (True, False):
                        yield (check_results, kernel, h, atol, rtol,
                               breadth_first)


def test_gaussian_kde(n_samples=1000):
    """Compare gaussian KDE results to scipy.stats.gaussian_kde"""
    from scipy.stats import gaussian_kde
    np.random.seed(0)
    x_in = np.random.normal(0, 1, n_samples)
    x_out = np.linspace(-5, 5, 30)

    for h in [0.01, 0.1, 1]:
        kdt = KDTree(x_in[:, None])
        try:
            gkde = gaussian_kde(x_in, bw_method=h / np.std(x_in))
        except TypeError:
            # older versions of scipy don't accept explicit bandwidth
            raise SkipTest

        dens_kdt = kdt.kernel_density(x_out[:, None], h) / n_samples
        dens_gkde = gkde.evaluate(x_out)

        assert_allclose(dens_kdt, dens_gkde, rtol=1E-3, atol=1E-3)


def test_kd_tree_two_point(n_samples=100, n_features=3):
    np.random.seed(0)
    X = np.random.random((n_samples, n_features))
    Y = np.random.random((n_samples, n_features))
    r = np.linspace(0, 1, 10)
    kdt = KDTree(X, leaf_size=10)

    D = DistanceMetric.get_metric("euclidean").pairwise(Y, X)
    counts_true = [(D <= ri).sum() for ri in r]

    def check_two_point(r, dualtree):
        counts = kdt.two_point_correlation(Y, r=r, dualtree=dualtree)
        assert_allclose(counts, counts_true)

    for dualtree in (True, False):
        yield check_two_point, r, dualtree


def test_kd_tree_pickle():
    import pickle
    np.random.seed(0)
    X = np.random.random((10, 3))
    kdt1 = KDTree(X, leaf_size=1)
    ind1, dist1 = kdt1.query(X)

    def check_pickle_protocol(protocol):
        s = pickle.dumps(kdt1, protocol=protocol)
        kdt2 = pickle.loads(s)
        ind2, dist2 = kdt2.query(X)
        assert_allclose(ind1, ind2)
        assert_allclose(dist1, dist2)

    for protocol in (0, 1, 2):
        yield check_pickle_protocol, protocol

def test_neighbors_heap(n_pts=5, n_nbrs=10):
    heap = NeighborsHeap(n_pts, n_nbrs)

    for row in range(n_pts):
        d_in = np.random.random(2 * n_nbrs).astype(DTYPE)
        i_in = np.arange(2 * n_nbrs, dtype=ITYPE)
        for d, i in zip(d_in, i_in):
            heap.push(row, d, i)

        ind = np.argsort(d_in)
        d_in = d_in[ind]
        i_in = i_in[ind]

        d_heap, i_heap = heap.get_arrays(sort=True)

        assert_allclose(d_in[:n_nbrs], d_heap[row])
        assert_allclose(i_in[:n_nbrs], i_heap[row])


def test_node_heap(n_nodes=50):
    vals = np.random.random(n_nodes).astype(DTYPE)

    i1 = np.argsort(vals)
    vals1 = vals[i1]
    vals2, i2 = nodeheap_sort(vals)

    assert_allclose(i1, i2)
    assert_allclose(vals[i1], vals2)


def test_simultaneous_sort(n_rows=10, n_pts=201):
    dist = np.random.random((n_rows, n_pts)).astype(DTYPE)
    ind = (np.arange(n_pts) + np.zeros((n_rows, 1))).astype(ITYPE)

    dist2 = dist.copy()
    ind2 = ind.copy()

    # simultaneous sort rows using function
    simultaneous_sort(dist, ind)
    
    # simultaneous sort rows using numpy
    i = np.argsort(dist2, axis=1)
    row_ind = np.arange(n_rows)[:, None]
    dist2 = dist2[row_ind, i]
    ind2 = ind2[row_ind, i]

    assert_allclose(dist, dist2)
    assert_allclose(ind, ind2)


def _test_find_split_dim():
    # check for several different random seeds
    for i in range(5):
        np.random.seed(i)
        data = np.random.random((50, 5)).astype(DTYPE)
        indices = np.arange(50, dtype=ITYPE)
        np.random.shuffle(indices)

        idx_start = 10
        idx_end = 40

        i_split = find_split_dim(data, indices, idx_start, idx_end)
        i_split_2 = np.argmax(np.max(data[indices[idx_start:idx_end]], 0) -
                              np.min(data[indices[idx_start:idx_end]], 0))

        assert_(i_split == i_split_2)


def _test_partition_indices():
    # check for several different random seeds
    for i in range(5):
        np.random.seed(i)

        data = np.random.random((50, 5)).astype(DTYPE)
        indices = np.arange(50, dtype=ITYPE)
        np.random.shuffle(indices)

        split_dim = 2
        split_index = 25
        idx_start = 10
        idx_end = 40

        partition_indices(data, indices, split_dim,
                          idx_start, split_index, idx_end)
    
        assert_(np.all(data[indices[idx_start:split_index], split_dim]
                       <= data[indices[split_index], split_dim]) and
                np.all(data[indices[split_index], split_dim]
                       <= data[indices[split_index:idx_end], split_dim]))


if __name__ == '__main__':
    import nose
    nose.runmodule()
