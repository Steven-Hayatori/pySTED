
import time
import numpy
import bleach_funcs
cimport numpy
cimport cython

from libc.math cimport exp
from libc.stdlib cimport rand, srand, RAND_MAX

INTDTYPE = numpy.int32
FLOATDTYPE = numpy.float64

ctypedef numpy.int32_t INTDTYPE_t
ctypedef numpy.float64_t FLOATDTYPE_t

@cython.boundscheck(False)  # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
def default_update_survival_probabilities(object self,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] i_ex,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] i_sted,
                   float p_ex,
                   float p_sted,
                   float step,
                   dict bleached_sub_datamaps_dict,
                   int row,
                   int col,
                   int h,
                   int w,
                   list mask,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] prob_ex,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] prob_sted,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] k_ex=None,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] k_sted=None,):
    cdef numpy.ndarray[FLOATDTYPE_t, ndim=2] photons_ex, photons_sted
    #cdef numpy.ndarray[FLOATDTYPE_t, ndim=2] k_ex, k_sted
    cdef int s, sprime, t, tprime
    cdef float prob
    cdef float rsamp
    cdef float maxval
    cdef float sampled_prob
    cdef int current
    cdef str key
    cdef float duty_cycle

    maxval = float(RAND_MAX)
    if k_sted is None:
        photons_ex = self.fluo.get_photons(i_ex * p_ex, self.excitation.lambda_)
        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(i_sted * p_sted * duty_cycle, self.sted.lambda_)
        k_sted = self.fluo.get_k_bleach(self.excitation.lambda_, self.sted.lambda_, photons_ex, photons_sted, self.sted.tau, 1/self.sted.rate, step, )
    if k_ex is None:
        k_ex = k_sted * 0.

    for key in bleached_sub_datamaps_dict:
        for (s, t) in mask:
            sprime = s - row
            tprime = t - col
        # for s in range(row, row + h):
        #     tprime = 0
        #     for t in range(col, col + w):
        #         # Updates probabilites
        #         # I THINK I COMPUTE THIS WETHER THE PIXEL WAS EMPTY OR NOT?
            prob_ex[s, t] = prob_ex[s, t] * exp(-1. * k_ex[sprime, tprime] * step)
            prob_sted[s, t] = prob_sted[s, t] * exp(-1. * k_sted[sprime, tprime] * step)
            #
            #     tprime += 1
            # sprime += 1


@cython.boundscheck(False)  # turn off bounds-checking for entire function
@cython.wraparound(False)  # turn off negative index wrapping for entire function
def sample_molecules(object self,
                   dict bleached_sub_datamaps_dict,
                   int row,
                   int col,
                   int h,
                   int w,
                   list mask,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] prob_ex,
                   numpy.ndarray[FLOATDTYPE_t, ndim=2] prob_sted):
    cdef int s, sprime, t, tprime, o
    cdef int sampled_value
    cdef float prob
    cdef float rsamp
    cdef float maxval
    cdef float sampled_prob
    cdef int current
    cdef str key

    maxval = float(RAND_MAX)

    for key in bleached_sub_datamaps_dict:
        for (s, t) in mask:
        #     sprime = s - row
        #     tprime = t - col
        # for s in range(row, row + h):
        #     for t in range(col, col + w):
            current = bleached_sub_datamaps_dict[key][s, t]
            if current > 0:
                # Calculates the binomial sampling
                sampled_value = 0
                prob = prob_ex[s, t] * prob_sted[s, t]
                # For each count we sample a random variable
                for o in range(current):
                    rsamp = rand()
                    sampled_prob = rsamp / maxval
                    if sampled_prob <= prob:
                        sampled_value += 1
                bleached_sub_datamaps_dict[key][s, t] = sampled_value
