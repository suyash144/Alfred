import numpy as np

nCells = 50
nStims = 500

fMax=4
th0 = np.random.rand(nCells)*2*np.pi
k = np.random.rand(nCells)
mix  = 1/(1+np.exp(np.random.randn(nCells)*2))

th = np.random.rand(nStims)*2*np.pi

def relu(x):
    return x*(x>0)

f1 = np.random.poisson(fMax * relu(np.cos(th[:,None]-th0[None,:])-k[None,:]))
f2 = np.random.poisson(fMax * relu(np.cos(th[:,None]-th0[None,:]-np.pi)-k[None,:]))

f = mix[None,:]*f1 + (1-mix[None,:])*f2

np.save(r'uploads/dir_tune.npy', f)
np.save(r'uploads/dirs.npy', th)