# -*- coding: utf-8 -*-
"""TEBD.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1jritSyAyHMNaUUk2tl9zTlI20pkksEtN
"""

import numpy as np
from numpy import linalg as LA
from scipy import special
from scipy.linalg import expm
from scipy.sparse.linalg import LinearOperator, eigs
from typing import List, Union, Tuple, Optional
import matplotlib.pyplot as plt

"""Define fucntion $ncon$ which contracts a tensor network of N tensors via a sequence of (N-1) tensordot operations."""

# Commented out IPython magic to ensure Python compatibility.
#tensor network contractor, by Glen Evenbly (c) for www.tensors.net
def ncon(tensors: List[np.ndarray],
         connects: List[Union[List[int], Tuple[int]]],
         con_order: Optional[Union[List[int], str]] = None,
         check_network: Optional[bool] = True,
         which_env: Optional[int] = 0):
  """
  Network CONtractor: contracts a tensor network of N tensors via a sequence
  of (N-1) tensordot operations. More detailed instructions and examples can
  be found at: https://arxiv.org/abs/1402.0939.
  Args:
    tensors: list of the tensors in the network.
    connects: length-N list of lists (or tuples) specifying the network
      connections. The jth entry of the ith list in connects labels the edge
      connected to the jth index of the ith tensor. Labels should be positive
      integers for internal indices and negative integers for free indices.
    con_order: optional argument to specify the order for contracting the
      positive indices. Defaults to ascending order if omitted. Can also be
      set at "greedy" or "full" to call a solver to automatically determine
      the order.
    check_network: if true then the input network is checked for consistency;
      this can catch many common user mistakes for defining networks.
    which_env: if provided, ncon will produce the environment of the requested
      tensor (i.e. the network given by removing the specified tensor from
      the original network). Only valid for networks with no open indices.
  Returns:
    Union[np.ndarray,float]: the result of the network contraction; an
      np.ndarray if the network contained open indices, otherwise a scalar.
  """
  num_tensors = len(tensors)
  tensor_list = [tensors[ele] for ele in range(num_tensors)]
  connect_list = [np.array(connects[ele]) for ele in range(num_tensors)]

  # generate contraction order if necessary
  flat_connect = np.concatenate(connect_list)
  if con_order is None:
    con_order = np.unique(flat_connect[flat_connect > 0])
  else:
    con_order = np.array(con_order)

  # check inputs if enabled
  if check_network:
    dims_list = [list(tensor.shape) for tensor in tensor_list]
    check_inputs(connect_list, flat_connect, dims_list, con_order)

  # do all partial traces
  for ele in range(len(tensor_list)):
    num_cont = len(connect_list[ele]) - len(np.unique(connect_list[ele]))
    if num_cont > 0:
      tensor_list[ele], connect_list[ele], cont_ind = partial_trace(
          tensor_list[ele], connect_list[ele])
      con_order = np.delete(
          con_order,
          np.intersect1d(con_order, cont_ind, return_indices=True)[1])

  # do all binary contractions
  while len(con_order) > 0:
    # identify tensors to be contracted
    cont_ind = con_order[0]
    locs = [
        ele for ele in range(len(connect_list))
        if sum(connect_list[ele] == cont_ind) > 0
    ]

    # do binary contraction
    cont_many, A_cont, B_cont = np.intersect1d(
        connect_list[locs[0]],
        connect_list[locs[1]],
        assume_unique=True,
        return_indices=True)
    if np.size(tensor_list[locs[0]]) < np.size(tensor_list[locs[1]]):
      ind_order = np.argsort(A_cont)
    else:
      ind_order = np.argsort(B_cont)

    tensor_list.append(
        np.tensordot(
            tensor_list[locs[0]],
            tensor_list[locs[1]],
            axes=(A_cont[ind_order], B_cont[ind_order])))
    connect_list.append(
        np.append(
            np.delete(connect_list[locs[0]], A_cont),
            np.delete(connect_list[locs[1]], B_cont)))

    # remove contracted tensors from list and update con_order
    del tensor_list[locs[1]]
    del tensor_list[locs[0]]
    del connect_list[locs[1]]
    del connect_list[locs[0]]
    con_order = np.delete(
        con_order,
        np.intersect1d(con_order, cont_many, return_indices=True)[1])

  # do all outer products
  while len(tensor_list) > 1:
    s1 = tensor_list[-2].shape
    s2 = tensor_list[-1].shape
    tensor_list[-2] = np.outer(tensor_list[-2].reshape(np.prod(s1)),
                               tensor_list[-1].reshape(np.prod(s2))).reshape(
                                   np.append(s1, s2))
    connect_list[-2] = np.append(connect_list[-2], connect_list[-1])
    del tensor_list[-1]
    del connect_list[-1]

  # do final permutation
  if len(connect_list[0]) > 0:
    return np.transpose(tensor_list[0], np.argsort(-connect_list[0]))
  else:
    return tensor_list[0].item()


def partial_trace(A, A_label):
  """ Partial trace on tensor A over repeated labels in A_label """

  num_cont = len(A_label) - len(np.unique(A_label))
  if num_cont > 0:
    dup_list = []
    for ele in np.unique(A_label):
      if sum(A_label == ele) > 1:
        dup_list.append([np.where(A_label == ele)[0]])

    cont_ind = np.array(dup_list).reshape(2 * num_cont, order='F')
    free_ind = np.delete(np.arange(len(A_label)), cont_ind)

    cont_dim = np.prod(np.array(A.shape)[cont_ind[:num_cont]])
    free_dim = np.array(A.shape)[free_ind]

    B_label = np.delete(A_label, cont_ind)
    cont_label = np.unique(A_label[cont_ind])
    B = np.zeros(np.prod(free_dim))
    A = A.transpose(np.append(free_ind, cont_ind)).reshape(
        np.prod(free_dim), cont_dim, cont_dim)
    for ip in range(cont_dim):
      B = B + A[:, ip, ip]

    return B.reshape(free_dim), B_label, cont_label

  else:
    return A, A_label, []


def check_inputs(connect_list, flat_connect, dims_list, con_order):
  """ Check consistancy of NCON inputs"""

  pos_ind = flat_connect[flat_connect > 0]
  neg_ind = flat_connect[flat_connect < 0]

  # check that lengths of lists match
  if len(dims_list) != len(connect_list):
    raise ValueError(
        ('mismatch between %i tensors given but %i index sublists given') %
        (len(dims_list), len(connect_list)))

  # check that tensors have the right number of indices
  for ele in range(len(dims_list)):
    if len(dims_list[ele]) != len(connect_list[ele]):
      raise ValueError((
          'number of indices does not match number of labels on tensor %i: '
          '%i-indices versus %i-labels')
#           % (ele, len(dims_list[ele]), len(connect_list[ele])))

  # check that contraction order is valid
  if not np.array_equal(np.sort(con_order), np.unique(pos_ind)):
    raise ValueError(('NCON error: invalid contraction order'))

  # check that negative indices are valid
  for ind in np.arange(-1, -len(neg_ind) - 1, -1):
    if sum(neg_ind == ind) == 0:
      raise ValueError(('NCON error: no index labelled %i') % (ind))
    elif sum(neg_ind == ind) > 1:
      raise ValueError(('NCON error: more than one index labelled %i') % (ind))

  # check that positive indices are valid and contracted tensor dimensions match
  flat_dims = np.array([item for sublist in dims_list for item in sublist])
  for ind in np.unique(pos_ind):
    if sum(pos_ind == ind) == 1:
      raise ValueError(('NCON error: only one index labelled %i') % (ind))
    elif sum(pos_ind == ind) > 2:
      raise ValueError(
          ('NCON error: more than two indices labelled %i') % (ind))

    cont_dims = flat_dims[flat_connect == ind]
    if cont_dims[0] != cont_dims[1]:
      raise ValueError(
          ('NCON error: tensor dimension mismatch on index labelled %i: '
           'dim-%i versus dim-%i') % (ind, cont_dims[0], cont_dims[1]))

  return True

"""Define fucntions implementing real/imaginary time evolution for MPS with 2-site unit cell (A-B), based on TEBD algorithm."""

# Implementation of time evolution (real or imaginary) for MPS with 2-site unit
# cell (A-B), based on TEBD algorithm.
#
# part by Glen Evenbly (c) for www.tensors.net, (v1.2) - last modified 6/2019
# part newly written to perform specific tasks wanted for this project

def doTEBD(hamAB: np.ndarray,
           hamBA: np.ndarray,
           A: np.ndarray,
           B: np.ndarray,
           sAB: np.ndarray,
           sBA: np.ndarray,
           chi: int,
           tau: float,
           evotype: Optional[str] = 'imag',
           numiter: Optional[int] = 1000,
           midsteps: Optional[int] = 10,
           E0: Optional[float] = 0.0,
           magz: Optional[np.ndarray] = None):
  """
  Implementation of time evolution (real or imaginary) for MPS with 2-site unit
  cell (A-B), based on TEBD algorithm.
  Args:
    hamAB: nearest neighbor Hamiltonian coupling for A-B sites.
    hamBA: nearest neighbor Hamiltonian coupling for B-A sites.
    A: MPS tensor for A-sites of lattice.
    B: MPS tensor for B-sites of lattice.
    sAB: vector of weights for A-B links.
    sBA: vector of weights for B-A links.
    chi: maximum bond dimension of MPS.
    tau: time-step of evolution.
    evotype: set real (evotype='real') or imaginary (evotype='imag') evolution.
    numiter: number of time-step iterations to take.
    midsteps: number of time-steps between re-orthogonalization of the MPS.
    E0: specify the ground energy (if known).
  Returns:
    np.ndarray: MPS tensor for A-sites;
    np.ndarray: MPS tensor for B-sites;
    np.ndarray: vector sAB of weights for A-B links.
    np.ndarray: vector sBA of weights for B-A links.
    np.ndarray: two-site reduced density matrix rhoAB for A-B sites
    np.ndarray: two-site reduced density matrix rhoAB for B-A sites
  """

  # exponentiate Hamiltonian
  d = A.shape[1]
  if evotype == "real":
    gateAB = expm(1j * tau * hamAB.reshape(d**2, d**2)).reshape(d, d, d, d)
    gateBA = expm(1j * tau * hamBA.reshape(d**2, d**2)).reshape(d, d, d, d)
  elif evotype == "imag":
    gateAB = expm(-tau * hamAB.reshape(d**2, d**2)).reshape(d, d, d, d)
    gateBA = expm(-tau * hamBA.reshape(d**2, d**2)).reshape(d, d, d, d)

  # initialize environment matrices
  sigBA = np.eye(A.shape[0]) / A.shape[0]
  muAB = np.eye(A.shape[2]) / A.shape[2]
  time = [] #define time array to store iteration steps
  sim_E_0 = [] #simulated ground state energy array as time evolved
  m_z = [] #expectation value of magnetisation along z direction

  for k in range(numiter + 1):
    if np.mod(k, midsteps) == 0 or (k == numiter):
      """ Bring MPS to normal form """

      # contract MPS from left and right
      sigBA, sigAB = left_contract_MPS(sigBA, sBA, A, sAB, B)
      muAB, muBA = right_contract_MPS(muAB, sBA, A, sAB, B)

      # orthogonalise A-B and B-A links
      B, sBA, A = orthog_MPS(sigBA, muBA, B, sBA, A)
      A, sAB, B = orthog_MPS(sigAB, muAB, A, sAB, B)

      # normalize the MPS tensors
      A_norm = np.sqrt(ncon([np.diag(sBA**2), A, np.conj(A), np.diag(sAB**2)],
                            [[1, 3], [1, 4, 2], [3, 4, 5], [2, 5]]))
      A = A / A_norm
      B_norm = np.sqrt(ncon([np.diag(sAB**2), B, np.conj(B), np.diag(sBA**2)],
                            [[1, 3], [1, 4, 2], [3, 4, 5], [2, 5]]))
      B = B / B_norm

      """ Compute energy and display """

      # compute 2-site local reduced density matrices
      rhoAB, rhoBA = loc_density_MPS(A, sAB, B, sBA)

      # evaluate the energy
      energyAB = ncon([hamAB, rhoAB], [[1, 2, 3, 4], [1, 2, 3, 4]])
      energyBA = ncon([hamBA, rhoBA], [[1, 2, 3, 4], [1, 2, 3, 4]])
      energy = 0.5 * (energyAB + energyBA)

      chitemp = min(A.shape[0], B.shape[0])
      enDiff = energy - E0
      '''print('iteration: %d of %d, chi: %d, t-step: %f, energy: %f, '
            'energy error: %e' % (k, numiter, chitemp, tau, energy, enDiff))'''
      time.append(k)
      sim_E_0.append(energy)


      """ real time evolution to find spin"""
      #evaluate the spin
      if magz is not None:
        mz_t = find_mz(A, sAB, B, sBA, magz)
        m_z.append(mz_t)



    """ Do evolution of MPS through one time-step """
    if k < numiter:
      # apply gate to A-B link
      A, sAB, B = apply_gate_MPS(gateAB, A, sAB, B, sBA, chi)

      # apply gate to B-A link
      B, sBA, A = apply_gate_MPS(gateBA, B, sBA, A, sAB, chi)


  rhoAB, rhoBA = loc_density_MPS(A, sAB, B, sBA)
  return A, B, sAB, sBA, rhoAB, rhoBA, time, sim_E_0, m_z


def left_contract_MPS(sigBA, sBA, A, sAB, B):
  """ Contract an infinite 2-site unit cell from the left for the environment
  density matrices sigBA (B-A link) and sigAB (A-B link)"""

  # initialize the starting vector
  chiBA = A.shape[0]
  if sigBA.shape[0] == chiBA:
    v0 = sigBA.reshape(np.prod(sigBA.shape))
  else:
    v0 = (np.eye(chiBA) / chiBA).reshape(chiBA**2)

  # define network for transfer operator contract
  tensors = [np.diag(sBA), np.diag(sBA), A, A.conj(), np.diag(sAB),
             np.diag(sAB), B, B.conj()]
  labels = [[1, 2], [1, 3], [2, 4], [3, 5, 6], [4, 5, 7], [6, 8], [7, 9],
            [8, 10, -1], [9, 10, -2]]

  # define function for boundary contraction and pass to eigs
  def left_iter(sigBA):
    return ncon([sigBA.reshape([chiBA, chiBA]), *tensors],
                labels).reshape([chiBA**2, 1])
  Dtemp, sigBA = eigs(LinearOperator((chiBA**2, chiBA**2), matvec=left_iter),
                      k=1, which='LM', v0=v0, tol=1e-10)

  # normalize the environment density matrix sigBA
  if np.isrealobj(A):
    sigBA = np.real(sigBA)
  sigBA = sigBA.reshape(chiBA, chiBA)
  sigBA = 0.5 * (sigBA + np.conj(sigBA.T))
  sigBA = sigBA / np.trace(sigBA)

  # compute density matric sigAB for A-B link
  sigAB = ncon([sigBA, np.diag(sBA), np.diag(sBA), A, np.conj(A)],
               [[1, 2], [1, 3], [2, 4], [3, 5, -1], [4, 5, -2]])
  sigAB = sigAB / np.trace(sigAB)

  return sigBA, sigAB


def right_contract_MPS(muAB, sBA, A, sAB, B):
  """ Contract an infinite 2-site unit cell from the right for the environment
  density matrices muAB (A-B link) and muBA (B-A link)"""

  # initialize the starting vector
  chiAB = A.shape[2]
  if muAB.shape[0] == chiAB:
    v0 = muAB.reshape(np.prod(muAB.shape))
  else:
    v0 = (np.eye(chiAB) / chiAB).reshape(chiAB**2)

  # define network for transfer operator contract
  tensors = [np.diag(sAB), np.diag(sAB), A, A.conj(), np.diag(sBA),
             np.diag(sBA), B, B.conj()]
  labels = [[1, 2], [3, 1], [5, 2], [6, 4, 3], [7, 4, 5], [8, 6], [10, 7],
            [-1, 9, 8], [-2, 9, 10]]

  # define function for boundary contraction and pass to eigs
  def right_iter(muAB):
    return ncon([muAB.reshape([chiAB, chiAB]), *tensors],
                labels).reshape([chiAB**2, 1])
  Dtemp, muAB = eigs(LinearOperator((chiAB**2, chiAB**2), matvec=right_iter),
                     k=1, which='LM', v0=v0, tol=1e-10)

  # normalize the environment density matrix muAB
  if np.isrealobj(A):
    muAB = np.real(muAB)
  muAB = muAB.reshape(chiAB, chiAB)
  muAB = 0.5 * (muAB + np.conj(muAB.T))
  muAB = muAB / np.trace(muAB)

  # compute density matrix muBA for B-A link
  muBA = ncon([muAB, np.diag(sAB), np.diag(sAB), A, A.conj()],
              [[1, 2], [3, 1], [5, 2], [-1, 4, 3], [-2, 4, 5]])
  muBA = muBA / np.trace(muBA)

  return muAB, muBA


def orthog_MPS(sigBA, muBA, B, sBA, A, dtol=1e-12):
  """ set the MPS gauge across B-A link to the canonical form """

  # diagonalize left environment matrix
  dtemp, utemp = LA.eigh(sigBA)
  chitemp = sum(dtemp > dtol)
  DL = dtemp[range(-1, -chitemp - 1, -1)]
  UL = utemp[:, range(-1, -chitemp - 1, -1)]

  # diagonalize right environment matrix
  dtemp, utemp = LA.eigh(muBA)
  chitemp = sum(dtemp > dtol)
  DR = dtemp[range(-1, -chitemp - 1, -1)]
  UR = utemp[:, range(-1, -chitemp - 1, -1)]

  # compute new weights for B-A link
  weighted_mat = (np.diag(np.sqrt(DL)) @ UL.T @ np.diag(sBA)
                  @ UR @ np.diag(np.sqrt(DR)))
  UBA, stemp, VhBA = LA.svd(weighted_mat, full_matrices=False)
  sBA = stemp / LA.norm(stemp)

  # build x,y gauge change matrices, implement gauge change on A and B
  x = np.conj(UL) @ np.diag(1 / np.sqrt(DL)) @ UBA
  y = np.conj(UR) @ np.diag(1 / np.sqrt(DR)) @ VhBA.T
  A = ncon([y, A], [[1, -1], [1, -2, -3]])
  B = ncon([B, x], [[-1, -2, 2], [2, -3]])

  return B, sBA, A


def apply_gate_MPS(gateAB, A, sAB, B, sBA, chi, stol=1e-7):
  """ apply a gate to an MPS across and a A-B link. Truncate the MPS back to
  some desired dimension chi"""

  # ensure singular values are above tolerance threshold
  sBA_trim = sBA * (sBA > stol) + stol * (sBA < stol)

  # contract gate into the MPS, then deompose composite tensor with SVD
  d = A.shape[1]
  chiBA = sBA_trim.shape[0]
  tensors = [np.diag(sBA_trim), A, np.diag(sAB), B, np.diag(sBA_trim), gateAB]
  connects = [[-1, 1], [1, 5, 2], [2, 4], [4, 6, 3], [3, -4], [-2, -3, 5, 6]]
  nshape = [d * chiBA, d * chiBA]
  utemp, stemp, vhtemp = LA.svd(ncon(tensors, connects).reshape(nshape),
                                full_matrices=False)

  # truncate to reduced dimension
  chitemp = min(chi, len(stemp))
  utemp = utemp[:, range(chitemp)].reshape(sBA_trim.shape[0], d * chitemp)
  vhtemp = vhtemp[range(chitemp), :].reshape(chitemp * d, chiBA)

  # remove environment weights to form new MPS tensors A and B
  A = (np.diag(1 / sBA_trim) @ utemp).reshape(sBA_trim.shape[0], d, chitemp)
  B = (vhtemp @ np.diag(1 / sBA_trim)).reshape(chitemp, d, chiBA)

  # new weights
  sAB = stemp[range(chitemp)] / LA.norm(stemp[range(chitemp)])

  return A, sAB, B


def loc_density_MPS(A, sAB, B, sBA):
  """ Compute the local reduced density matrices from an MPS (assumend to be
  in canonical form)."""

  # recast singular weights into a matrix
  mAB = np.diag(sAB)
  mBA = np.diag(sBA)

  # contract MPS for local reduced density matrix (A-B)
  tensors = [np.diag(sBA**2), A, A.conj(), mAB, mAB, B, B.conj(),
             np.diag(sBA**2)]
  connects = [[3, 4], [3, -3, 1], [4, -1, 2], [1, 7], [2, 8], [7, -4, 5],
              [8, -2, 6], [5, 6]]
  rhoAB = ncon(tensors, connects)

  # contract MPS for local reduced density matrix (B-A)
  tensors = [np.diag(sAB**2), B, B.conj(), mBA, mBA, A, A.conj(),
             np.diag(sAB**2)]
  connects = [[3, 4], [3, -3, 1], [4, -1, 2], [1, 7], [2, 8], [7, -4, 5],
              [8, -2, 6], [5, 6]]
  rhoBA = ncon(tensors, connects)

  return rhoAB, rhoBA


def single_density(A, sAB, B, sBA):
  mAB = np.diag(sAB)
  mBA = np.diag(sBA)

  tensors = [(mBA @ mBA), A, (mAB @ mAB), A.conj()]
  #tensors = [np.diag(sBA**2), A, np.diag(sAB**2), A.conj()]
  labels = [[1 ,2], [2, -2, 3], [3, 4], [1, -1, 4]]
  '''print('chi = %d, d = %d' %(chi, d))
  print('dim of sAB is ', np.shape(sAB))
  print('dim of mAB is ', np.shape(mAB))
  print('dim of (mAB@mAB) is', np.shape(mAB @ mAB))
  print('dim of A is', np.shape(A))'''
  rhoA = ncon(tensors, labels)

  tensors = [(mAB @ mAB), B, (mBA @ mBA), B.conj()]
  #tensors = [np.diag(sAB**2), B, np.diag(sBA**2), B.conj()]
  rhoB = ncon(tensors, labels)

  return rhoA, rhoB

def find_mz(A, sAB, B, sBA, mz):
    rhoA, rhoB = single_density(A, sAB, B, sBA)
    mzA = ncon([mz, rhoA], [[1, 2], [1, 2]])
    mzB = ncon([mz, rhoB], [[1, 2], [1, 2]])
    mz_t = 0.5 * (mzA + mzB)
    return mz_t


def theory_e0(h):
  ld = 1 / (2*h)
  theta = 2 * np.sqrt(ld) / (1 + ld)
  eq = special.ellipe(theta**2)
  E_per_site = -1* h * 2 * (1 + ld) * eq / np.pi
  #E_per_site = -1 * 2 * (h + 1/2) * eq / np.pi #reexpressed form
  return E_per_site

"""Scripts initialising the Hamiltonian and MPS tensors and allowed to evolve by TEBD."""

"""
Script for initializing the Hamiltonian and MPS tensors before passing to
the TEBD routine.

"""

"""
Model used: 1D transverse Ising model with longitudinal field, with reference to G. Vidal (2007)
"""
numiter = 900  # number of timesteps
evotype = "imag"  # real or imaginary time evolution
E0 = -4 / np.pi  # specify exact ground energy (not known, just plug in random number, since this does not affect simulation performed here)
tau = 0.1  # timestep
midsteps = int(1 / tau)  # timesteps between MPS re-orthogonalization

# define Hamiltonian (quantum XX model)
sX = np.array([[0, 1], [1, 0]])
sY = np.array([[0, -1j], [1j, 0]])
sZ = np.array([[1, 0], [0, -1]])




""" Imaginary time evolution with TEBD """
# set bond dimensions and simulation options
chi = 16  # bond dimension
tau = 0.1  # timestep
# run TEBD routine
hz = np.linspace(0.0, 5.0, 10)
theory =[]
sim_e = []
error4 = []
error16 = []


#varying chi value, and also checking the accuracy of the simulation in finding ground state energy
for h in hz:
  # initialize tensors
  d = hamAB.shape[0]
  sAB = np.ones(chi) / np.sqrt(chi)
  sBA = np.ones(chi) / np.sqrt(chi)
  A = np.random.rand(chi, d, chi)
  B = np.random.rand(chi, d, chi)
  hamAB = (np.real(np.kron(sX, sX) + h*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
  hamBA = hamAB
  _, _, _, _, _, _, _, E_0 = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)
  tebd_e = E_0[-1]
  expected = theory_e0(h)
  percent_err = (tebd_e - expected)*100/expected
  sim_e.append(tebd_e)
  theory.append(expected)
  error16.append(percent_err)

chi = 4
for h in hz:
  # initialize tensors
  d = hamAB.shape[0]
  sAB = np.ones(chi) / np.sqrt(chi)
  sBA = np.ones(chi) / np.sqrt(chi)
  A = np.random.rand(chi, d, chi)
  B = np.random.rand(chi, d, chi)
  hamAB = (np.real(np.kron(sX, sX) + h*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
  hamBA = hamAB
  _, _, _, _, _, _, _, E_0= doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)
  tebd_e = E_0[-1]
  expected = theory_e0(h)
  percent_err = (tebd_e - expected)*100/expected
  sim_e.append(tebd_e)
  theory.append(expected)
  error4.append(percent_err)


plt.plot(hz, error4, '.', label = '$\chi = 4$')
plt.plot(hz, error16, '.', label = '$\chi = 16$')
plt.xlabel('$h_z$')
plt.ylabel('Error, in %')
plt.title('Percentage error in ground state energy, timestep = 0.1')
plt.legend(loc = 'upper right', bbox_to_anchor = (0.9, 0.95))
plt.show()

""" Real time evolution to find mz(t) """
# set bond dimensions and simulation options
chi = 16  # bond dimension
# run TEBD routine
hz = np.linspace(0.0, 5.0, 40)
dh = 0.125
sim_mz_gs = []
sim_mz_realT = []


""" finding average spin by finding expectaion value of ground state found by imaginary time evolution """

#case 1: evolve system to ground state then examiine the real time dynamics of system
for h in hz:
  # initialize tensors
  hamAB = (np.real(-np.kron(sX, sX) - h*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
  hamBA = hamAB
  d = hamAB.shape[0]
  sAB = np.ones(chi) / np.sqrt(chi)
  sBA = np.ones(chi) / np.sqrt(chi)
  A = np.random.rand(chi, d, chi)
  B = np.random.rand(chi, d, chi)
  mag_z = sZ
  A1, B1, sAB1, sBA1, _, _, _, _, _ = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=450, midsteps=midsteps, E0=E0, magz = None)
  mz = find_mz(A1, sAB1, B1, sBA1, mag_z)
  sim_mz_gs.append(mz)
  A2, B2, sAB2, sBA2, _, _, _, _, real_mz_sim = doTEBD(hamAB, hamBA, A1, B1, sAB1, sBA1, chi,
    tau, evotype="real", numiter=100, midsteps=midsteps, E0=E0, magz = mag_z)
  realT_mz = real_mz_sim[-1]
  sim_mz_realT.append(realT_mz)

plt.plot(time, real_mz_sim)
plt.ylabel('$m_z$')
plt.xlabel('time')
plt.title('Real time evolution of average magnetisation, $\chi$ = %d, h = %f'%(chi, h1))
plt.show()


#case 2: evolve system to ground state then find the average spin of the ground state
for h in hz:
  # initialize tensors
  hamAB = (np.real(-np.kron(sX, sX) - h*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
  hamBA = hamAB
  d = hamAB.shape[0]
  sAB = np.ones(chi) / np.sqrt(chi)
  sBA = np.ones(chi) / np.sqrt(chi)
  A = np.random.rand(chi, d, chi)
  B = np.random.rand(chi, d, chi)
  mag_z = sZ
  A1, B1, sAB1, sBA1, _, _, _, _, _ = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=450, midsteps=midsteps, E0=E0, magz = sZ)
  mz = find_mz(A1, sAB1, B1, sBA1, mag_z)
  sim_mz_gs.append(mz)

plt.plot(hz, sim_mz_gs, '+', label = '$m_z$')
plt.plot(hz, np.gradient(sim_mz_gs, dh), '.', label = '$\partial m_z / \partial h$')
plt.ylabel('$m_z$')
plt.xlabel('$h_z$')
plt.title('Average magnetisation vs B field, $\chi$ = %d'%chi)
plt.legend(loc = 'lower right', bbox_to_anchor = (0.9, 0.1))
plt.show()


#case 3: first evolve system at one field to ground state, then change the B field and investigate the real time dynamics
# initialize tensors
h1 = 9.0
hamAB = (np.real(-np.kron(sX, sX) - h1*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
hamBA = hamAB
d = hamAB.shape[0]
sAB = np.ones(chi) / np.sqrt(chi)
sBA = np.ones(chi) / np.sqrt(chi)
A = np.random.rand(chi, d, chi)
B = np.random.rand(chi, d, chi)
mag_z = sZ
A1, B1, sAB1, sBA1, _, _, _, _, _ = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
  tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)

h2 = 0.8
hamAB2 = (np.real(-np.kron(sX, sX) - h2*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
hamBA2 = hamAB2
_, _, _, _, _, _, time, _, real_mz_sim = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
  tau, evotype='real', numiter=numiter, midsteps=midsteps, E0=E0,magz = sZ)

plt.plot(time, real_mz_sim)
plt.ylabel('$m_z$')
plt.xlabel('time')
plt.title('Real time evolution of average magnetisation, $\chi$ = %d, h = %f'%(chi, h1))
plt.show()


#checking: (done before all above cases) checking the contraction indexing of single_density function defined above
h = 0.9
hamAB = (np.real(np.kron(sX, sX) + h*np.kron(sZ, np.eye(2)))).reshape(2, 2, 2, 2)
hamBA = hamAB
d = hamAB.shape[0]
sAB = np.ones(chi) / np.sqrt(chi)
sBA = np.ones(chi) / np.sqrt(chi)
A = np.random.rand(chi, d, chi)
B = np.random.rand(chi, d, chi)
A1, B1, sAB1, sBA1, _, _, _, _ = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)
print('dim of A is', np.shape(A1))
print('dim of B is', np.shape(B1))
print('dim of sAB is', np.shape(sAB1))
print('dim of sBA is', np.shape(sBA1))
print(find_mz(A1, sAB1, B1, sBA1, sZ))
print('h =', h)


#for plotting some of the cases above
plt.plot(time, mz_t, label = '$m_z$')
plt.ylabel('$m_z$')
plt.xlabel('time')
plt.title('Average magnetisation vs time, $\chi$ = %d'%chi)


plt.plot(hz, sim_mz_gs, label = 'From ground state, by imaginary time evolution ')
plt.plot(hz, sim_mz_realT, '+', label = 'From real time evolution of system')
plt.ylabel('$m_z$')
plt.xlabel('$h_z$')
plt.title('Average magnetisation vs B field, $\chi$ = %d'%chi)
plt.legend(loc = 'lower right', bbox_to_anchor = (0.9, 0.1))
plt.show()

A, B, sAB, sBA, rhoAB, rhoBA, time, E_0 = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)


# continute running TEBD routine with reduced timestep
tau = 0.01
numiter = 2000
midsteps = 100
A, B, sAB, sBA, rhoAB, rhoBA, time, E_0 = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)


# continute running TEBD routine with reduced timestep and increased bond dim
chi = 32
tau = 0.001
numiter = 20000
midsteps = 1000
A, B, sAB, sBA, rhoAB, rhoBA, time, E_0 = doTEBD(hamAB, hamBA, A, B, sAB, sBA, chi,
    tau, evotype=evotype, numiter=numiter, midsteps=midsteps, E0=E0)




#subplots showing error as well as ground energy at each h value
ax1 = plt.subplot(211)
#plt.plot(time, E_0, label = '$E_0$')
plt.plot(hz, theory,label = 'theory')
plt.plot(hz, sim_e, '.', label = 'simulation')
plt.ylabel('$E_0$/N')
plt.xlabel('h')
plt.title('Ground state energy per site vs B field, $\chi$ = %d, timestep = %f'%(chi, tau))
plt.legend(loc = 'upper right', bbox_to_anchor = (0.9, 0.95))

ax2 = plt.subplot(212, sharex=ax1)
plt.plot(hz, error, '+', label = 'Percentage error')
plt.tick_params('x', labelbottom=False)
plt.ylabel('Error in %')
plt.legend()

plt.show()


plt.plot(hz, error, label = '$\chi = 16$')
plt.ylabel('Error, in %')
plt.xlabel('h')
plt.title('Percentage error in gorund state energy, timestep =  %f'%tau)
plt.legend(loc = 'upper right', bbox_to_anchor = (0.9, 0.95))
plt.show()