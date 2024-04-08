import numpy as np
from matplotlib import pyplot as plt
import time

from pysted import base, utils, microscopes
from pysted import exp_data_gen as dg
from datetime import datetime
from PIL import Image
import simple_functions

"""
This script will go over the basics of pySTED for simulation of confocal and STED acquisitions
on simulated samples.
In order to simulate an acquisition, we need a microscope and a sample. To build the STED microscope, we need an
excitation beam, a STED beam, a detector and the parameters of the fluorophores used in the sample. The class
code for the objects that make up the microscope and the sample are contained in pysted.base
Each object has parameters which can be tuned, which will affect the resulting acquisition
"""

print("Setting up the microscope...")
# Fluorophore properties
egfp = {
    "lambda_": 535e-9,
    "qy": 0.6,
    "sigma_abs": {
        488: 0.08e-21,
        575: 0.02e-21
    },
    "sigma_ste": {
        575: 3.0e-22,
    },
    "tau": 3e-09,
    "tau_vib": 1.0e-12,
    "tau_tri": 1.2e-6,
    "k1": 1.3e-15, # Atto640N, Oracz2017
    "b":1.4, # Atto640N, Oracz2017
    "triplet_dynamics_frac": 0,
}

pixelsize = 20e-9
# Generating objects necessary for acquisition simulation
laser_ex = base.GaussianBeam(488e-9)
laser_sted = base.DonutBeam(575e-9, zero_residual=0, rate=40e6, tau=400e-12, anti_stoke=False)  #Similar to the labs microscope
detector = base.Detector(noise=True, det_delay=750e-12, det_width=8e-9, background=0) #Similar to the labs microscope
objective = base.Objective()
fluo = base.Fluorescence(**egfp)

# These are the parameter ranges our RL agents can select from when playing actions
action_spaces = {
    "p_sted" : {"low" : 0., "high" : 175e-3}, # Similar to the sted in our lab
    "p_ex" : {"low" : 0., "high" : 150e-6}, # Similar to the sted in our lab
    "pdt" : {"low" : 10.0e-6, "high" : 150.0e-6},
}

# Example values of parameters used when doing a STED acquisition
sted_params = {
    "pdt": action_spaces["pdt"]["low"] * 2,
    "p_ex": action_spaces["p_ex"]["high"] * 0.6,
    "p_sted": action_spaces["p_sted"]["high"] * 0.6
}

# Example values of parameters used when doing a Confocal acquisition. Confocals always have p_sted = 0
conf_params = {
    "pdt": action_spaces["pdt"]["low"],
    "p_ex": action_spaces["p_ex"]["high"] * 0.6,
    "p_sted": 0.0   # params have to be floats to pass the C function
}

# generate the microscope from its constituent parts
# if load_cache is true, it will load the previously generated microscope. This can save time if a
# microscope was previsously generated and used the same pixelsize we are using now
microscope = base.Microscope(laser_ex, laser_sted, detector, objective, fluo, load_cache=True)
i_ex, i_sted, _ = microscope.cache(pixelsize, save_cache=True)
psf_conf = microscope.get_effective(pixelsize, action_spaces["p_ex"]["high"], 0.0)
psf_sted = microscope.get_effective(pixelsize, action_spaces["p_ex"]["high"], action_spaces["p_sted"]["high"] * 0.25)

# 背景突触
def normalization(img):
    min_val = np.min(img)
    max_val = np.max(img)
    stretched_array = ((img - min_val) / (max_val - min_val)) * 255
    stretched_array = stretched_array.astype(np.uint8)
    return stretched_array


def generation(STRENGTH_BG, STRENGTH_MO, NUM_MO, SEED_BG, SEED_MO, i):
    simple_functions.log(f'背景强度{STRENGTH_BG}, 荧光强度{STRENGTH_MO}, 荧光数{NUM_MO}, 种子A{SEED_BG}, 种子B{SEED_MO},这是第{i+1}张生成')
    shroom1 = dg.Synapse(STRENGTH_BG, mode="custom", seed=SEED_BG)

    n_molecs_in_domain1, min_dist1 = STRENGTH_MO, 50
    shroom1.add_nanodomains(NUM_MO, min_dist_nm=min_dist1, n_molecs_in_domain=n_molecs_in_domain1, valid_thickness=2, seed=SEED_MO)

    # create the Datamap and set its region of interest
    dmap = base.Datamap(shroom1.frame, pixelsize)
    dmap.set_roi(i_ex, "max")

    conf_acq, conf_bleached, _ = microscope.get_signal_and_bleach(dmap, dmap.pixelsize, **conf_params, bleach=True, update=False, seed=42)
    sted_acq, sted_bleached, _ = microscope.get_signal_and_bleach(dmap, dmap.pixelsize, **sted_params, bleach=True, update=True, seed=42)

    # fig, axes = plt.subplots(1,3)
    # vmax = conf_acq.max()
    # axes[0].imshow(dmap.whole_datamap[dmap.roi])
    # axes[0].set_title(f"Datamap")
    # axes[1].imshow(conf_acq, vmax=vmax)
    # axes[1].set_title(f"Confocal")
    # vmax = sted_acq.max()
    # axes[2].imshow(sted_acq, vmax=vmax)
    # axes[2].set_title(f"STED")

    Image.fromarray(normalization(conf_acq)).save(f'./output/Confocal/{i}.png')
    Image.fromarray(normalization(sted_acq)).save(f'./output/STED/{i}.png')
    simple_functions.log(f'第{i+1}次生成完成')