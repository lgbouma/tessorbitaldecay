#!/usr/bin/env bash

##########################################
# USAGE: ./measure_wasp4b_times_ast.sh &> ../logs/wasp4b.log &
# (note &> pipes stdout and stderr. then second & runs as bkgd process.)
##########################################

cd ../src

chain_savdir='/home/luke/local/emcee_chains/'
n_mcmc=1000
n_phase_mcmc=1000 #  at 1000, 15 minutes per phase transit. (30 total), 
n_workers=16 # number of workers on ast!
n_transit_durations=2


ticid=437248515 # WASP-31b
lcdir='/home/luke/local/tess_mast_lightcurves/tic_'${ticid}'/'
python -u measure_transit_times_from_lightcurve.py \
  --ticid $ticid --n_mcmc_steps $n_mcmc \
  --n_phase_mcmc_steps $n_phase_mcmc \
  --no-getspocparams --read_literature_params \
  --overwritesamples --no-mcmcprogressbar \
  --nworkers $n_workers --chain_savdir $chain_savdir --lcdir $lcdir \
  --no-verify-times \
  --n_transit_durations $n_transit_durations

exit 1

# ticid=22529346 # WASP-121b
# lcdir='/home/luke/local/tess_mast_lightcurves/tic_'${ticid}'/'
# python -u measure_transit_times_from_lightcurve.py \
#   --ticid $ticid --n_mcmc_steps $n_mcmc \
#   --n_phase_mcmc_steps $n_phase_mcmc \
#   --no-getspocparams --read_literature_params \
#   --overwritesamples --no-mcmcprogressbar \
#   --nworkers $n_workers --chain_savdir $chain_savdir --lcdir $lcdir \
#   --no-verify-times \
#   --n_transit_durations $n_transit_durations
# 
# exit 1

# ticid=36352297 # CoRoT-1b
# lcdir='/home/luke/local/tess_mast_lightcurves/tic_'${ticid}'/'
# python -u measure_transit_times_from_lightcurve.py \
#   --ticid $ticid --n_mcmc_steps $n_mcmc \
#   --n_phase_mcmc_steps $n_phase_mcmc \
#   --no-getspocparams --read_literature_params \
#   --overwritesamples --no-mcmcprogressbar \
#   --nworkers $n_workers --chain_savdir $chain_savdir --lcdir $lcdir \
#   --no-verify-times \
#   --n_transit_durations $n_transit_durations
# 
# exit 1

# ticid=35516889 # WASP-19b
# lcdir='/home/luke/local/tess_mast_lightcurves/tic_'${ticid}'/'
# python -u measure_transit_times_from_lightcurve.py \
#   --ticid $ticid --n_mcmc_steps $n_mcmc \
#   --n_phase_mcmc_steps $n_phase_mcmc \
#   --no-getspocparams --read_literature_params \
#   --overwritesamples --no-mcmcprogressbar \
#   --nworkers $n_workers --chain_savdir $chain_savdir --lcdir $lcdir \
#   --no-verify-times \
#   --n_transit_durations $n_transit_durations
# 

exit 1

ticid=17746821 # HAT-P-50b
lcdir='/home/luke/local/tess_mast_lightcurves/tic_'${ticid}'/'
python -u measure_transit_times_from_lightcurve.py \
  --ticid $ticid --n_mcmc_steps $n_mcmc \
  --n_phase_mcmc_steps $n_phase_mcmc \
  --no-getspocparams --read_literature_params \
  --overwritesamples --no-mcmcprogressbar \
  --nworkers $n_workers --chain_savdir $chain_savdir --lcdir $lcdir \
  --no-verify-times \
  --n_transit_durations $n_transit_durations
