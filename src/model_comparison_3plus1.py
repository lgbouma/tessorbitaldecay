# -*- coding: utf-8 -*-
"""
description
-----

4 models:

    1) Linear fit
    2) Quadratic fit (broad priors; it doesn't matter)
    3) Precession fit (k2 ~ BROAD)
    4) Precession fit (k2 ~ U[0.015, 1.5])

usage
-----

$ python model_comparison_linear_quadratic_precession.py | tee
    ../results/model_comparison_3plus1/WASP-4b/model_comparison_3plus1_output.txt
"""

from __future__ import division, print_function

import matplotlib as mpl
mpl.use('Agg')
import numpy as np, matplotlib.pyplot as plt, pandas as pd
import seaborn as sns

from numpy import array as nparr
from scipy import stats, optimize, integrate
from astropy import units as u, constants as const

import emcee, corner
from datetime import datetime
import os, argparse, pickle, h5py
from glob import glob
from multiprocessing import Pool

from parse import search

#############
## LOGGING ##
#############

import logging
from datetime import datetime
from traceback import format_exc

# setup a logger
LOGGER = None
LOGMOD = __name__
DEBUG = False

def set_logger_parent(parent_name):
    globals()['LOGGER'] = logging.getLogger('%s.%s' % (parent_name, LOGMOD))

def LOGDEBUG(message):
    if LOGGER:
        LOGGER.debug(message)
    elif DEBUG:
        print('[%s - DBUG] %s' % (
            datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            message)
        )

def LOGINFO(message):
    if LOGGER:
        LOGGER.info(message)
    else:
        print('[%s - INFO] %s' % (
            datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            message)
        )

def LOGERROR(message):
    if LOGGER:
        LOGGER.error(message)
    else:
        print('[%s - ERR!] %s' % (
            datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            message)
        )

def LOGWARNING(message):
    if LOGGER:
        LOGGER.warning(message)
    else:
        print('[%s - WRN!] %s' % (
            datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            message)
        )

def LOGEXCEPTION(message):
    if LOGGER:
        LOGGER.exception(message)
    else:
        print(
            '[%s - EXC!] %s\nexception was: %s' % (
                datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
                message, format_exc()
            )
        )



###############################
# initial wrangling functions #
###############################

def get_data(
    datacsv='../data/WASP-18b_transits_and_TESS_times_O-C_vs_epoch_selected.csv',
    is_occultation=False
    ):
    # need to run make_parameter_vs_epoch_plots.py first; this generates the
    # SELECTED epochs (x values), mid-times (y values), and mid-time errors
    # (sigma_y).

    df = pd.read_csv(datacsv, sep=';')

    tcol = [c for c in nparr(df.columns) if
            ('times_BJD_TDB_minus_' in c) and ('minutes' in c)]
    if len(tcol) != 1:
        raise AssertionError('unexpected input file')
    else:
        tcol = tcol[0]

    if is_occultation:
        err_column = 'err_sel_occ_times_BJD_TDB_minutes'
    else:
        err_column = 'err_sel_transit_times_BJD_TDB_minutes'

    data = nparr( [
        nparr(df['sel_epoch']),
        nparr(df[tcol]),
        nparr(df[err_column])
    ])

    x, y, sigma_y = data
    refs = nparr(df['original_reference'])

    return x, y, sigma_y, data, tcol, refs


def initial_plot_data(x, y, sigma_y, savpath=None, xlabel='x', ylabel='y'):

    fig, ax = plt.subplots(figsize=(6,4))
    ax.errorbar(x, y, sigma_y, fmt='ok', ecolor='gray');
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title('transits we will fit')

    fig.tight_layout()
    fig.savefig(savpath, bbox_inches='tight', dpi=350)


def plot_maxlikelihood_models(
    x, y, sigma_y, theta_linear, theta_quadratic,
    savpath=os.path.join('../results/model_comparison_3plus1/toy_model',
                         'data_maxlikelihood_fits.png'),
    xlabel='x', ylabel='y'):

    xfit = np.linspace(np.min(x), np.max(x), 1000)

    fig, ax = plt.subplots(figsize=(6,4))

    ax.errorbar(x, y, sigma_y, fmt='ok', ecolor='lightgray', elinewidth=1)
    ax.plot(xfit, polynomial_fit(theta_linear, xfit),
            label='best linear model')
    ax.plot(xfit, polynomial_fit(theta_quadratic, xfit),
            label='best quadratic model')

    ax.legend(loc='best', fontsize='x-small')
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    fig.tight_layout()
    fig.savefig(savpath, bbox_inches='tight', dpi=350)


def plot_maxlikelihood_OminusC(
    x, y, sigma_y, theta_linear, theta_quadratic, theta_precession=None,
    savpath=os.path.join('../results/model_comparison_3plus1/toy_model',
                         'data_maxlikelihood_OminusC.png'),
    xlabel='epoch', ylabel='deviation from constant period [min]',
    legendstr='max likelihood',
    x_occ=None, y_occ=None, sigma_y_occ=None):

    xfit = np.linspace(np.min(x), np.max(x), 1000)

    if (
        isinstance(x_occ,np.ndarray)
        and
        isinstance(y_occ,np.ndarray)
        and
        isinstance(sigma_y_occ,np.ndarray)
        and
        'WASP-18b' in savpath
        and
        legendstr == 'median MCMC'
    ):
        plt.close('all')
        xfit = np.linspace(np.min(x)-1000, np.max(x)+1000, 1000)
        xfit_occ = np.linspace(np.min(x)-1000, np.max(x)+1000, 1000)

        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(6,4))

        _, caps, bars = ax.errorbar(x,
                    y-linear_fit(theta_linear, x),
                    sigma_y, marker='.', color='k', ecolor='gray', zorder=2, capsize=0,
                    capthick=0, lw=1, ls='none'
                    )
        [bar.set_alpha(0.8) for bar in bars]
        [cap.set_alpha(0.8) for cap in caps]

        ax.plot(xfit,
                linear_fit(theta_linear, xfit)
                    - linear_fit(theta_linear, xfit),
                label='Best linear fit', zorder=-2)
        ax.plot(xfit,
                quadratic_fit(theta_quadratic, xfit)
                    - linear_fit(theta_linear, xfit),
                label='Best quadratic fit', zorder=-1)

        _, caps, bars = ax.errorbar(x_occ,
                   y_occ-linear_fit(theta_linear, x, x_occ=x_occ)[1],
                   sigma_y_occ, marker='.', color='gray', ecolor='gray',
                   zorder=2, capsize=0, capthick=0, lw=1, ls='none')
        [bar.set_alpha(0.3) for bar in bars]
        [cap.set_alpha(0.3) for cap in caps]

        _,caps,bars = ax.errorbar(42,42,1,
                                  marker='.', color='black',
                                  ecolor='gray', zorder=-3,
                                  label='Transits', ls='none')
        [bar.set_alpha(0.8) for bar in bars]
        [cap.set_alpha(0.8) for cap in caps]

        _,caps,bars = ax.errorbar(42,42,1, marker='.', color='gray',
                                  ecolor='gray', zorder=-3,
                                  label='Occultations', ls='none')
        [bar.set_alpha(0.3) for bar in bars]
        [cap.set_alpha(0.3) for cap in caps]

        ax.legend(loc='best', fontsize='small')
        ax.get_yaxis().set_tick_params(which='both', direction='in')
        ax.get_xaxis().set_tick_params(which='both', direction='in')

        ax.set_ylim((-3,3))
        ax.set_xlim((-4600,1100))

        fig.text(0.5,0, 'Epoch', ha='center', fontsize='large')
        fig.text(0,0.5, 'Transit timing residuals [minute]', va='center',
                 rotation=90, fontsize='large')
        fig.tight_layout(h_pad=0, w_pad=0)
        outpath = savpath.replace('.png','_occ-tra.png')
        fig.savefig(outpath, bbox_inches='tight', dpi=350)
        LOGINFO('made {:s}'.format(outpath))

    if (
        isinstance(x_occ,np.ndarray)
        and
        isinstance(y_occ,np.ndarray)
        and
        isinstance(sigma_y_occ,np.ndarray)
    ):
        xfit_occ = np.linspace(np.min(x), np.max(x), 1000)

        fig, (a0,a1) = plt.subplots(nrows=2, ncols=1, figsize=(6,4),
                                    sharex=True)

        a0.errorbar(x,
                    y-linear_fit(theta_linear, x),
                    sigma_y, fmt='.k', ecolor='gray', zorder=2)
        a0.plot(xfit,
                linear_fit(theta_linear, xfit)
                    - linear_fit(theta_linear, xfit),
                label='{:s} linear fit'.format(legendstr), zorder=-2)
        a0.plot(xfit,
                quadratic_fit(theta_quadratic, xfit)
                    - linear_fit(theta_linear, xfit),
                label='{:s} quadratic fit'.format(legendstr), zorder=-1)
        if isinstance(theta_precession, np.ndarray):
            a0.plot(xfit,
                    precession_fit_k2p_params(theta_precession, xfit)
                        - linear_fit(theta_linear, xfit),
                    label='{:s} precession fit'.format(legendstr), zorder=-1)

        a1.errorbar(x_occ,
                   y_occ-linear_fit(theta_linear, x, x_occ=x_occ)[1],
                   sigma_y_occ, fmt='.k', ecolor='gray', zorder=2)
        a1.plot(xfit_occ,
               linear_fit(theta_linear, xfit, x_occ=xfit_occ)[1]
                   - linear_fit(theta_linear, xfit, x_occ=xfit_occ)[1],
               label='{:s} linear fit'.format(legendstr), zorder=-2)
        a1.plot(xfit_occ,
               quadratic_fit(theta_quadratic, xfit, x_occ=xfit_occ)[1]
                   - linear_fit(theta_linear, xfit, x_occ=xfit_occ)[1],
               label='{:s} quadratic fit'.format(legendstr), zorder=-1)
        if isinstance(theta_precession, np.ndarray):
            a1.plot(xfit_occ,
                    precession_fit_k2p_params(theta_precession, xfit, x_occ=xfit_occ)[1]
                        - linear_fit(theta_linear, xfit, x_occ=xfit_occ)[1],
                    label='{:s} precession fit'.format(legendstr), zorder=-1)

        a1.legend(loc='best', fontsize='x-small')
        for ax in (a0,a1):
            ax.get_yaxis().set_tick_params(which='both', direction='in')
            ax.get_xaxis().set_tick_params(which='both', direction='in')

        fig.text(0.5,0, xlabel, ha='center')
        fig.text(0,0.5, ylabel, va='center', rotation=90)
        fig.tight_layout(h_pad=0, w_pad=0)
        fig.savefig(savpath, bbox_inches='tight', dpi=350)
        LOGINFO('made {:s}'.format(savpath))

    else:
        fig, ax = plt.subplots(figsize=(6,4))

        ax.errorbar(x,
                    y-polynomial_fit(theta_linear, x),
                    sigma_y, fmt='ok', ecolor='gray', zorder=2)
        ax.plot(xfit,
                polynomial_fit(theta_linear, xfit)
                    - polynomial_fit(theta_linear, xfit),
                label='{:s} linear fit'.format(legendstr), zorder=-2)
        ax.plot(xfit,
                polynomial_fit(theta_quadratic, xfit)
                    - polynomial_fit(theta_linear, xfit),
                label='{:s} quadratic fit'.format(legendstr), zorder=-1)
        if isinstance(theta_precession, np.ndarray):
            ax.plot(xfit,
                    precession_fit_k2p_params(theta_precession, xfit)
                        - polynomial_fit(theta_linear, xfit),
                    label='{:s} precession fit'.format(legendstr), zorder=-1)

        ax.legend(loc='best', fontsize='x-small')
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

        fig.tight_layout()
        fig.savefig(savpath, bbox_inches='tight', dpi=350)
        LOGINFO('made {:s}'.format(savpath))


def linear_fit(theta, x, x_occ=None):
    """
    Linear model. Parameters (t0, P).
    Must pass transit times.

    If x_occ is none, returns model t_tra array.
    If x_occ is a numpy array, returns tuple of model t_tra and t_occ arrays.
    """
    t0, period = theta
    if not isinstance(x_occ,np.ndarray):
        return t0 + period*x
    else:
        return t0 + period*x, t0 + period/2 + period*x_occ

def quadratic_fit(theta, x, x_occ=None):
    """
    Quadratic model. Parameters (t0, P, 0.5dP/dE).
    Must pass transit times.

    If x_occ is none, returns model t_tra array.
    If x_occ is a numpy array, returns tuple of model t_tra and t_occ arrays.
    """
    t0, period, half_dP_dE = theta
    if not isinstance(x_occ,np.ndarray):
        return t0 + period*x + half_dP_dE*x**2
    else:
        return (t0 + period*x + half_dP_dE*x**2,
                t0 + period/2 + period*x_occ + half_dP_dE*x_occ**2
               )

def precession_fit(theta, x, x_occ=None):
    """
    Precession model. Parameters (t0, P_s, e, omega0, domega_by_dE).
    Must pass transit times.

    If x_occ is none, returns model t_tra array.
    If x_occ is a numpy array, returns tuple of model t_tra and t_occ arrays.
    """
    t0, P_s, e, omega0, domega_by_dΕ = theta
    P_a = P_s * (1 - domega_by_dΕ/(2*np.pi))**(-1)

    if not isinstance(x_occ,np.ndarray):
        return (
            t0 + P_s*x -
            ( (e/np.pi) * P_a *
              np.cos( omega0 + domega_by_dΕ*x)
            )
        )
    else:
        return (
            t0 + P_s*x -
            ( (e/np.pi) * P_a *
              np.cos( omega0 + domega_by_dΕ*x)
            ),
            t0 + P_a/2 + P_s*x_occ +
            ( (e/np.pi) * P_a *
              np.cos( omega0 + domega_by_dΕ*x_occ)
            )
        )


def precession_fit_k2p_params(theta, x, x_occ=None, Mstar=0.864,
                              Mplanet=1.186):
    """
    Precession model. Parameters (t0, P_s, e, omega0, k2p, Rplanet, semimaj).
    Must pass transit & occ times.

    If x_occ is none, returns model t_tra array.
    If x_occ is a numpy array, returns tuple of model t_tra and t_occ arrays.

    Defaults are set to WASP-4, b/c it's probably the only (near-term) case
    that seems relevant.
    """

    t0, P_s, e, omega0, k2p, Rplanet, semimaj = theta

    domega_by_dΕ = (
        15*np.pi * k2p * ((Rplanet*u.Rjup/(semimaj*u.AU)).cgs.value)**5
        * (Mstar*u.Msun/(Mplanet*u.Mjup)).cgs.value
    )

    P_a = P_s * (1 - domega_by_dΕ/(2*np.pi))**(-1)

    if not isinstance(x_occ,np.ndarray):
        return (
            t0 + P_s*x -
            ( (e/np.pi) * P_a *
              np.cos( omega0 + domega_by_dΕ*x)
            )
        )
    else:
        return (
            t0 + P_s*x -
            ( (e/np.pi) * P_a *
              np.cos( omega0 + domega_by_dΕ*x)
            ),
            t0 + P_a/2 + P_s*x_occ +
            ( (e/np.pi) * P_a *
              np.cos( omega0 + domega_by_dΕ*x_occ)
            )
        )



def polynomial_fit(theta, x):
    """
    Polynomial model of degree (len(theta) - 1).
    E.g.,:
        tmid = t0 + P*x
        tmid = t0 + P*x + (1/2)dP/dE * x^2,
    etc.
    """

    return sum(t * x ** n for (n, t) in enumerate(theta))


def best_theta(degree, data, data_occ=None):
    """Standard frequentist approach: find the model that maximizes the
    likelihood under each model. Here, do it by direct optimization."""

    # create a zero vector of inital values
    theta_0 = np.zeros(degree+1)

    neg_logL = lambda theta: -log_likelihood(theta, data, data_occ=data_occ)

    return optimize.fmin_bfgs(neg_logL, theta_0, disp=False)


def ml_precession(data, data_occ=None, init_theta=None, domega_dE_min=5e-4,
                  e_max=0.1, e_min=1e-4, domega_dE_max=3e-3):
    """Direct optimize the likelihood for the precession model. Impose some
    inequality constraints to help the COBYLA."""

    # theta: reference epoch, P_sidereal, eccentricity, argument of periastron
    # at reference epoch, precession rate.
    if not (isinstance(init_theta,list) or isinstance(init_theta,np.ndarray)):
        raise AssertionError
    theta_0 = init_theta

    neg_logL = lambda theta: -log_likelihood_precession(theta, data,
                                                        data_occ=data_occ)

    ##########################
    # inequality constraints #
    ##########################
    # dω/dE > 0
    constr0 = lambda theta: theta[4]
    # ω0 > 0
    constr1 = lambda theta: theta[3]
    # 2π - ω0 > 0. 1 & 2 same as saying ω0 in [0,2π].
    constr2 = lambda theta: 2*np.pi - theta[3]
    # e > 0
    constr3 = lambda theta: theta[2]
    # e < 0.1 ==> 0.1 - e > 0
    constr4 = lambda theta: e_max - theta[2]
    # dω/dE < 3e-3 ==> 3e-3 - dω/dE > 0
    constr5 = lambda theta: domega_dE_max - theta[4]
    # dω/dE > 5e-4 ==> dω/dE - 1e-4 > 0
    constr6 = lambda theta: theta[4] - domega_dE_min
    # e > 1e-4 ==> e - 1e-4 > 0
    constr7 = lambda theta: theta[2] - e_min

    constraints_dict= (
        {'type':'ineq', 'fun':constr0},
        {'type':'ineq', 'fun':constr1},
        {'type':'ineq', 'fun':constr2},
        {'type':'ineq', 'fun':constr3},
        {'type':'ineq', 'fun':constr4},
        {'type':'ineq', 'fun':constr5},
        {'type':'ineq', 'fun':constr6},
        {'type':'ineq', 'fun':constr7}
    )

    return optimize.minimize(neg_logL, theta_0, method='COBYLA',
                             constraints=constraints_dict)


#########################
# frequentist functions #
#########################

def compute_chi2(degree, data, data_occ=None):

    x, y, sigma_y = data
    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ

    theta = best_theta(degree, data, data_occ=data_occ)

    if degree == 1:
        model=linear_fit
    elif degree == 2:
        model=quadratic_fit

    resid = (y - model(theta, x)) / sigma_y
    chi2 = np.sum(resid ** 2)
    if isinstance(data_occ,np.ndarray):
        resid_occ = (y_occ - model(theta, x, x_occ=x_occ)[1]) / sigma_y_occ
        chi2 += np.sum(resid_occ ** 2)

    return chi2


def chi2_maxlike(degree, data, data_occ=None):

    k = degree + 1 # number of free parameters
    n = data.shape[1] # number of data points
    if isinstance(data_occ,np.ndarray):
        n += data_occ.shape[1]

    chi2 = compute_chi2(degree, data, data_occ=data_occ)
    dof = n-k

    AIC = chi2 + 2*k
    BIC = chi2 + k*np.log(n)

    print('degree: {:d}\tchi2: {:.6g}\tdof: {:d}\tAIC: {:.2e}\tBIC: {:.2e}'
          .format(degree, chi2, int(dof), AIC, BIC))

    return stats.chi2(dof).pdf(chi2), AIC, BIC


def chi2_bestfit_posterior(degree, data, theta_bestfit, data_occ=None):
    # compute maximum likehood, and print out associated chi^2 stats.
    # theta_bestfit is the median of the MCMC sample.

    k = degree + 1 # number of free parameters
    n = data.shape[1] # number of data points
    if isinstance(data_occ,np.ndarray):
        n += data_occ.shape[1]

    if degree == 1:
        model=linear_fit
    elif degree == 2:
        model=quadratic_fit

    # get chi2
    x, y, sigma_y = data
    resid = (y - model(theta_bestfit, x)) / sigma_y
    chi2 = np.sum(resid ** 2)
    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ
        resid_occ = (y_occ - model(theta_bestfit, x, x_occ=x_occ)[1]) / sigma_y_occ
        chi2 += np.sum(resid_occ ** 2)

    dof = n-k

    AIC = chi2 + 2*k
    BIC = chi2 + k*np.log(n)

    print('degree: {:d}\tchi2: {:.6g}\tdof: {:d}\tAIC: {:.2e}\tBIC: {:.2e}'
          .format(degree, chi2, int(dof), AIC, BIC))

    return stats.chi2(dof).pdf(chi2), AIC, BIC


def chi2_bestfit_precession(data, theta_bestfit, data_occ=None):
    # compute maximum likehood, and print out associated chi^2 stats.
    # theta_bestfit is the median of the MCMC sample.

    k = len(theta_bestfit) # number of free parameters
    n = data.shape[1] # number of data points
    if isinstance(data_occ,np.ndarray):
        n += data_occ.shape[1]

    # get chi2
    x, y, sigma_y = data
    resid = (y - precession_fit_k2p_params(theta_bestfit, x)) / sigma_y
    chi2 = np.sum(resid ** 2)

    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ
        resid_occ = (
            (y_occ - precession_fit_k2p_params(theta_bestfit, x, x_occ=x_occ)[1])
            /
            sigma_y_occ
        )
        chi2 += np.sum(resid_occ ** 2)

    dof = n-k

    AIC = chi2 + 2*k
    BIC = chi2 + k*np.log(n)

    print('precession-- \tchi2: {:.6g}\tdof: {:d}\tAIC: {:.2e}\tBIC: {:.2e}'
          .format(chi2, int(dof), AIC, BIC))

    return stats.chi2(dof).pdf(chi2), AIC, BIC





def plot_chi2_diff_distribution_comparison(
    data,
    data_occ=None,
    savpath=(
        os.path.join('../results/model_comparison_3plus1/toy_model',
                     'chi2_diff_distribution_comparison.png'))
    ):

    chi2_diff = (
        compute_chi2(1, data, data_occ=data_occ)
        -
        compute_chi2(2, data, data_occ=data_occ)
    )

    # The p value in this context means that, assuming the linear model is
    # true, there is a 17% probability that simply by chance we would see data
    # that favors the quadratic model more strongly than the data we have.
    v = np.linspace(1e-3, 120, 10000)
    chi2_dist = stats.chi2(1).pdf(v)
    # Calculate p value through survival function of the chi2 distribution.
    p_value = stats.chi2(1).sf(chi2_diff)

    fig, ax = plt.subplots(figsize=(6,4))
    ax.fill_between(v, 0, chi2_dist, alpha=0.3)
    ax.fill_between(v, 0, chi2_dist * (v > chi2_diff), alpha=0.5)
    ax.axvline(chi2_diff)

    ax.set_ylim((0, 1))
    ax.set_xlabel("$\chi^2_{\mathrm{linear}} - \chi^2_{\mathrm{quadratic}}$")
    ax.set_ylabel("probability")
    ax.set_yscale("log")
    ax.set_ylim([1e-24,1])

    ax.text(0.97, 0.97, "p = {:.3e}".format(p_value),
            ha='right', va='top', transform=ax.transAxes)

    fig.tight_layout()
    fig.savefig(savpath, bbox_inches='tight', dpi=350)

    return p_value

######################
# bayesian functions #
######################

def log10uniform(low=0, high=1, size=None):
    return 10**(np.random.uniform(low, high, size))


def log_prior(theta, plparams, delta_period = 1e-5*24*60, delta_t0 = 3):
    """
      theta[0]: t0, theta[1]: P, theta[2]: 1/2 dP/dE

      prob(t0) ~ U(t0-small number, t0+small number) [small # := 3 minutes]
      prob(P) ~ U(P-small number, P+small number) [small # := 1e-5 days]
      prob( 1/2 dP/dE ) ~ U( convert to Qstar! )

    from Eq 14 and 6 of Patra+ 2017,
    theta2 = 1/2 dP/dE = -1/2 P * 27*pi/(2*Qstar)*Mp/Mstar*(Rstar/a)^5.
    Qstar can be between say U[1e3,1e9].

    args:
        theta (np.ndarray): vector of parameters, in order listed above.
        plparams (tuple of floats): see order below.

    kwargs:
        delta_period (float): both in units of MINUTES, used to set bounds of
        uniform priors.
    """

    Rstar, Mplanet, Mstar, semimaj, nominal_period, nominal_t0 = plparams
    Qstar_low = 1e3
    # Qstar_high = 1e12

    theta2_low = (
        -1/2 * nominal_period * 27 * np.pi / (2*Qstar_low) * Mplanet/Mstar
        * (Rstar / semimaj)**5
    ).to(u.minute).value

    # NOTE: the below prior is what you would use if you are ASSUMING a
    # negative period derivative. However it is better to let the data speak.
    # By default, do not assume this. Let Qstar vary from [1e3 to -1e3], in
    # other words let a positive period derivative be in the prior too.
    # theta2_high = (
    #     -1/2 * nominal_period * 27 * np.pi / (2*Qstar_high) * Mplanet/Mstar
    #     * (Rstar / semimaj)**5
    # ).to(u.minute).value
    theta2_high = -theta2_low

    # now impose the prior on each parameter
    if len(theta)==2:
        t0, P = theta

        if ((nominal_period.value-delta_period < P <
             nominal_period.value+delta_period) and
            (nominal_t0.value-delta_t0 < t0 <
             nominal_t0.value+delta_t0)
           ):

            return 0.

        return -np.inf

    elif len(theta)==3:
        t0, P, theta2 = theta

        if ((nominal_period.value-delta_period < P <
             nominal_period.value+delta_period) and
            (nominal_t0.value-delta_t0 < t0 <
             nominal_t0.value+delta_t0) and
            (theta2_low < theta2 < theta2_high)
           ):

            return 0.

        return -np.inf

    else:
        raise NotImplementedError


def _get_domega_by_dE_given_k2(k2p, Mp=1.186*u.Mjup, Mstar=0.864*u.Msun,
                               a=0.0226*u.AU, Rp=1.321*u.Rjup):
    # Patra et al (2017) equation 16., which is from Ragozzine & Wolf '09
    # eqn 14.
    Mstar_by_Mp = (Mstar/Mp).cgs.value
    Rplanet_by_a = (Rp/a).cgs.value
    return k2p * 15*np.pi * Mstar_by_Mp * Rplanet_by_a**5


def log_prior_precession(theta, plparams, delta_period = 1e-1*24*60,
                         delta_t0 = 10*60, impose_k2p_physical=False):
    """
    args:
        theta (np.ndarray): vector of parameters, in order listed above.

        plparams (tuple of floats): see order below.

    kwargs:
        delta_period (float): both in units of MINUTES, used to set bounds of
        uniform priors.
        Note Patra+2017 had sidereal period 1e-5 days different from orbital
        period -> need a "large-ish" delta_period.
    """


    Rstar, Mplanet, Mstar, _, nominal_period, nominal_t0 = plparams

    t0, P_side, e, omega0, k2p, Rplanet, semimaj = theta

    t0_lower, t0_upper = nominal_t0.value-delta_t0, nominal_t0.value+delta_t0
    P_side_lower, P_side_upper = (
        nominal_period.value-delta_period, nominal_period.value+delta_period
    )

    # eccentricty upper set by Husnoo+ 2012: 0.011
    e_lower, e_upper = 1e-8, 0.011
    omega0_lower, omega0_upper = 0, 2*np.pi

    # # dω_by_dΕ_upper here avoids multimodality.
    # domega_by_dΕ_lower, domega_by_dΕ_upper = 1e-6, 3e-3

    if impose_k2p_physical:
        k2_p_upper = 1.5
        k2_p_lower = 0.015
    else:
        k2_p_upper = 15
        k2_p_lower = 0.0015

    # uniform part of prior.
    if not ((P_side_lower < P_side < P_side_upper) and
        (t0_lower < t0 < t0_upper) and
        (e_lower < e < e_upper) and
        (omega0_lower < omega0 < omega0_upper) and
        (k2_p_lower < k2p < k2_p_upper)
       ):

        return -np.inf

    # normal part of prior.
    mu_Rplanet, sigma_Rplanet = 1.321, 0.039
    mu_semimaj, sigma_semimaj = 0.0226, 0.0008

    logprior = (
        np.log(1.0/(np.sqrt(2*np.pi)*sigma_Rplanet))
            -0.5*(Rplanet-mu_Rplanet)**2/sigma_Rplanet**2
        + np.log(1.0/(np.sqrt(2*np.pi)*sigma_semimaj))
            -0.5*(semimaj-mu_semimaj)**2/sigma_semimaj**2
    )

    return logprior


def log_likelihood(theta, data, data_occ=None):

    if len(theta)==2:
        model=linear_fit
    elif len(theta)==3:
        model=quadratic_fit

    # unpack the data
    x, y, sigma_y = data
    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ

    # evaluate the model at theta
    if not isinstance(data_occ,np.ndarray):
        y_fit = model(theta, x)
    else:
        y_fit, y_fit_occ = model(theta, x, x_occ=x_occ)

    # calculate the log likelihood
    if not isinstance(data_occ,np.ndarray):
        return -0.5 * np.sum(np.log(2 * np.pi * sigma_y ** 2)
                             + (y - y_fit) ** 2 / sigma_y ** 2)
    else:
        return -0.5 * (
            np.sum(np.log(2 * np.pi * sigma_y ** 2)
                   + (y - y_fit) ** 2 / sigma_y ** 2)
            +
            np.sum(np.log(2 * np.pi * sigma_y_occ ** 2)
                   + (y_occ - y_fit_occ) ** 2 / sigma_y_occ ** 2)
        )


def log_likelihood_precession(theta, data, data_occ=None):

    x, y, sigma_y = data
    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ

    # evaluate the model at theta
    if not isinstance(data_occ,np.ndarray):
        y_fit = precession_fit_k2p_params(theta, x)
    else:
        y_fit, y_fit_occ = precession_fit_k2p_params(theta, x, x_occ=x_occ)

    if not isinstance(data_occ,np.ndarray):
        return -0.5 * np.sum(np.log(2 * np.pi * sigma_y ** 2)
                             + (y - y_fit) ** 2 / sigma_y ** 2)
    else:
        return -0.5 * (
            np.sum(np.log(2 * np.pi * sigma_y ** 2)
                   + (y - y_fit) ** 2 / sigma_y ** 2)
            +
            np.sum(np.log(2 * np.pi * sigma_y_occ ** 2)
                   + (y_occ - y_fit_occ) ** 2 / sigma_y_occ ** 2)
        )


def log_posterior(theta, data, plparams, data_occ=None):

    theta = np.asarray(theta)

    lp = log_prior(theta, plparams)

    if not np.isfinite(lp):
        return -np.inf

    return lp + log_likelihood(theta, data, data_occ=data_occ)


def log_posterior_precession(theta, data, plparams, data_occ=None,
                             impose_k2p_physical=False):

    theta = np.asarray(theta)

    lp = log_prior_precession(theta, plparams,
                              impose_k2p_physical=impose_k2p_physical)

    if not np.isfinite(lp):
        return -np.inf

    return lp + log_likelihood_precession(theta, data, data_occ=data_occ)



def integrate_posterior_2D(posterior, xlim, ylim, data, plparams,
                           logprobs=True):

    if(logprobs):
        func = (
            lambda theta1, theta0:
            np.exp(log_posterior([theta0, theta1], data, plparams))
        )

    else:
        func = (
            lambda theta1, theta0: posterior([theta0, theta1], data, plparams)
        )

    return integrate.dblquad(func, xlim[0], xlim[1],
                             lambda x: ylim[0], lambda x: ylim[1],
                             epsabs=1e-1)


def integrate_posterior_3D(log_posterior, xlim, ylim, zlim, data, plparams,
                           logprobs=True):

    if(logprobs):
        func = (
            lambda theta2, theta1, theta0:
            np.exp(log_posterior([theta0, theta1, theta2], data, plparams))
        )

    else:
        func = (
            lambda theta2, theta1, theta0:
            posterior([theta0, theta1, theta2], data, plparams)
        )

    return integrate.tplquad(
        func, xlim[0], xlim[1],
        lambda x: ylim[0], lambda x: ylim[1],
        lambda x, y: zlim[0], lambda x, y: zlim[1],
        epsabs=1e-1
    )


def compute_mcmc(degree, data, plparams, theta_maxlike, plname, data_occ=None,
                 log_posterior=log_posterior, sampledir=None, n_walkers=50,
                 burninpercent=0.3, max_n_steps=1000,
                 overwriteexistingsamples=True, nworkers=8, plotcorner=True,
                 verbose=True, eps=1e-5, plotdir=None):

    if degree == 1:
        fitparamnames=['t0 [min]','P [min]']
    elif degree == 2:
        fitparamnames=['t0 [min]','P [min]','0.5 dP/dE [min]']
    else:
        raise NotImplementedError('this compares linear & quadratic fits')

    n_dim = degree + 1  # this determines the model

    samplesavpath = (
        sampledir+plname+
        '_degree{:d}_polynomial_timing_fit.h5'.format(degree)
    )
    backend = emcee.backends.HDFBackend(samplesavpath)
    if overwriteexistingsamples:
        LOGWARNING('erased samples previously at {:s}'.format(samplesavpath))
        backend.reset(n_walkers, n_dim)

    # if this is the first run, then start from a gaussian ball.
    # otherwise, resume from the previous samples.
    if isinstance(eps, float):
        starting_positions = (
            theta_maxlike + eps*np.random.randn(n_walkers, n_dim)
        )
    elif isinstance(eps, list) and degree==2:

        #NOTE: this should work. but perhaps better to sample over the log?
        starting_positions = (
            theta_maxlike[:,None] + nparr( [
            eps[0]*np.random.randn(n_walkers, 1).flatten(),
            eps[1]*np.random.randn(n_walkers, 1).flatten(),
            eps[2]*log10uniform(low=-5, high=-10, size=n_walkers),
            ] )
        ).T

    else:
        raise NotImplementedError

    isfirstrun = True
    if os.path.exists(backend.filename):
        if backend.iteration > 1:
            starting_positions = None
            isfirstrun = False

    if verbose and isfirstrun:
        LOGINFO(
            'start MCMC with {:d} dims, {:d} steps, {:d} walkers,'.format(
                n_dim, max_n_steps, n_walkers
            ) + ' {:d} threads'.format(nworkers)
        )
    elif verbose and not isfirstrun:
        LOGINFO(
            'continue with {:d} dims, {:d} steps, {:d} walkers, '.format(
                n_dim, max_n_steps, n_walkers
            ) + '{:d} threads'.format(nworkers)
        )

    # NOTE: new, can avoid annoyance of tuning n_steps
    index = 0
    autocorr = np.empty(max_n_steps)
    old_tau = np.inf

    sampler = emcee.EnsembleSampler(n_walkers, n_dim, log_posterior,
                                    args=(data, plparams, data_occ),
                                    backend=backend)

    for sample in sampler.sample(starting_positions, iterations=max_n_steps,
                                 progress=True):

        if sampler.iteration % 100:
            continue

        # compute autocorrleation time so far. tol=0 -> get an estimate,
        # even if it's not trustworthy
        tau = sampler.get_autocorr_time(tol=0)
        autocorr[index] = np.mean(tau)
        index += 1

        # check convergence
        converged = np.all(tau*100 < sampler.iteration)
        converged &= np.all(np.abs(old_tau - tau) / tau < 0.01)
        if converged:
            break
        old_tau = tau
        print(tau)

    # NOTE: old, works
    # with Pool(nworkers) as pool:
    #     sampler = emcee.EnsembleSampler(
    #         n_walkers, n_dim, log_posterior,
    #         args=(data, plparams, data_occ),
    #         pool=pool,
    #         backend=backend
    #     )
    #     sampler.run_mcmc(starting_positions, max_n_steps,
    #                      progress=False)

    if verbose:
        LOGINFO(
            'ended MCMC run with max {:d} steps, {:d} walkers, '.format(
                max_n_steps, n_walkers
            ) + '{:d} threads'.format(nworkers)
        )

    reader = emcee.backends.HDFBackend(samplesavpath)
    n_steps_taken = reader.iteration

    n_to_discard = int(burninpercent*n_steps_taken)

    samples = reader.get_chain(discard=n_to_discard, flat=True)
    log_prob_samples = reader.get_log_prob(discard=n_to_discard, flat=True)
    log_prior_samples = reader.get_blobs(discard=n_to_discard, flat=True)

    # Get best-fit parameters, their 1-sigma error bars, and the associated
    # limits
    fit_statistics = list(
        map(lambda v: (v[1], v[2]-v[1], v[1]-v[0],
                       v[0], v[3], v[4],
                       v[5], v[6], v[7]),
        list(zip(*np.percentile(
            samples,
            [15.85, 50, 84.15, 100-97.73, 100-99.87, 84.15, 97.73, 99.87],
            axis=0))))
    )

    (medianparams, std_perrs, std_merrs,
     onesigma_lower, twosigma_lower, threesigma_lower,
     onesigma_upper, twosigma_upper, threesigma_upper) = (
         {},{},{},{},{},{},{},{},{}
     )
    for ix, k in enumerate(fitparamnames):
        medianparams[k] = fit_statistics[ix][0]
        std_perrs[k] = fit_statistics[ix][1]
        std_merrs[k] = fit_statistics[ix][2]
        onesigma_lower[k] = fit_statistics[ix][3]
        twosigma_lower[k] = fit_statistics[ix][4]
        threesigma_lower[k] = fit_statistics[ix][5]
        onesigma_upper[k] = fit_statistics[ix][6]
        twosigma_upper[k] = fit_statistics[ix][7]
        threesigma_upper[k] = fit_statistics[ix][8]

    x, y, sigma_y = data
    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ
    if not isinstance(data_occ,np.ndarray):
        returndict = {
            'fittype':'degree_{:d}_polynomial'.format(degree),
            'fitinfo':{
                'initial_guess':theta_maxlike,
                'maxlikeparams':theta_maxlike,
                'medianparams':medianparams,
                'std_perrs':std_perrs,
                'std_merrs':std_merrs,
                'onesigma_lower':onesigma_lower,
                'twosigma_lower':twosigma_lower,
                'threesigma_lower':threesigma_lower,
                'onesigma_upper':onesigma_upper,
                'twosigma_upper':twosigma_upper,
                'threesigma_upper':threesigma_upper
            },
            'samplesavpath':samplesavpath,
            'data':{
                'epoch':x,
                'tmid_minus_offset':y,
                'err_tmid':sigma_y,
            },
        }
    elif isinstance(data_occ,np.ndarray):
        returndict = {
            'fittype':'degree_{:d}_polynomial'.format(degree),
            'fitinfo':{
                'initial_guess':theta_maxlike,
                'maxlikeparams':theta_maxlike,
                'medianparams':medianparams,
                'std_perrs':std_perrs,
                'std_merrs':std_merrs,
                'onesigma_lower':onesigma_lower,
                'twosigma_lower':twosigma_lower,
                'threesigma_lower':threesigma_lower,
                'onesigma_upper':onesigma_upper,
                'twosigma_upper':twosigma_upper,
                'threesigma_upper':threesigma_upper
            },
            'samplesavpath':samplesavpath,
            'data':{
                'epoch':x,
                'tmid_minus_offset':y,
                'err_tmid':sigma_y,
                'epoch_occ':x_occ,
                'tocc_minus_offset_occ':y_occ,
                'err_tmid_occ':sigma_y_occ,
            },
        }

    if plotcorner:
        if not plotdir:
            plotdir = os.path.join('../results/model_comparison_3plus1/',plname)
        cornersavpath = os.path.join(
            plotdir, 'corner_degree_{:d}_polynomial.png'.format(degree))

        fig = corner.corner(
            samples,
            labels=fitparamnames,
            truths=theta_maxlike,
            quantiles=[0.16, 0.5, 0.84], show_titles=True
        )

        fig.savefig(cornersavpath, dpi=300)
        if verbose:
            LOGINFO('saved {:s}'.format(cornersavpath))

    return returndict


def compute_mcmc_precession(data, plparams, theta_maxlike, plname,
                            data_occ=None, sampledir=None, n_walkers=50,
                            burninpercent=0.3, max_n_steps=1000,
                            overwriteexistingsamples=True, nworkers=8,
                            plotcorner=True, verbose=True, eps=None,
                            plotdir=None, impose_k2p_physical=False):

    fitparamnames=['t0 [min]','P_side [min]','e','omega0','k2p','Rp','a']
    n_dim = len(fitparamnames)

    savstr = '_wideprior' if not impose_k2p_physical else '_physprior'
    samplesavpath = (
        sampledir+plname+
        '_precession_timing_fit{}.h5'.format(savstr)
    )
    backend = emcee.backends.HDFBackend(samplesavpath)
    if overwriteexistingsamples:
        LOGWARNING('erased samples previously at {:s}'.format(samplesavpath))
        backend.reset(n_walkers, n_dim)

    # if this is the first run, then start from a gaussian ball.
    # otherwise, resume from the previous samples.
    if isinstance(eps, list):

        starting_positions = (
            theta_maxlike[:,None] + nparr( [
            eps[0]*np.random.randn(n_walkers, 1).flatten(),
            eps[1]*np.random.randn(n_walkers, 1).flatten(),
            eps[2]*log10uniform(low=-4, high=-3, size=n_walkers),
            eps[3]*np.random.randn(n_walkers, 1).flatten(),
            eps[4]*np.random.randn(n_walkers, 1).flatten(),
            eps[5]*np.random.randn(n_walkers, 1).flatten(),
            eps[6]*np.random.randn(n_walkers, 1).flatten()
            ] )
        ).T

    else:
        raise AssertionError('must pass eps as list of starting pushes')

    isfirstrun = True
    if os.path.exists(backend.filename):
        if backend.iteration > 1:
            starting_positions = None
            isfirstrun = False

    if verbose and isfirstrun:
        LOGINFO(
            'start MCMC with {:d} dims, {:d} steps, {:d} walkers,'.format(
                n_dim, max_n_steps, n_walkers
            ) + ' {:d} threads'.format(nworkers)
        )
    elif verbose and not isfirstrun:
        LOGINFO(
            'continue with {:d} dims, {:d} steps, {:d} walkers, '.format(
                n_dim, max_n_steps, n_walkers
            ) + '{:d} threads'.format(nworkers)
        )

    with Pool(nworkers) as pool:
        sampler = emcee.EnsembleSampler(
            n_walkers, n_dim, log_posterior_precession,
            args=(data, plparams, data_occ, impose_k2p_physical),
            pool=pool,
            backend=backend
        )
        sampler.run_mcmc(starting_positions, max_n_steps,
                         progress=True)

    if verbose:
        LOGINFO(
            'ended MCMC run with {:d} steps, {:d} walkers, '.format(
                max_n_steps, n_walkers
            ) + '{:d} threads'.format(nworkers)
        )

    reader = emcee.backends.HDFBackend(samplesavpath)

    n_to_discard = int(burninpercent*max_n_steps)

    samples = reader.get_chain(discard=n_to_discard, flat=True)
    log_prob_samples = reader.get_log_prob(discard=n_to_discard, flat=True)
    log_prior_samples = reader.get_blobs(discard=n_to_discard, flat=True)

    # Get best-fit parameters and their 1-sigma error bars
    fit_statistics = list(
        map(lambda v: (v[1], v[2]-v[1], v[1]-v[0]),
            list(zip( *np.percentile(samples, [16, 50, 84], axis=0))))
    )

    medianparams, std_perrs, std_merrs = {}, {}, {}
    for ix, k in enumerate(fitparamnames):
        medianparams[k] = fit_statistics[ix][0]
        std_perrs[k] = fit_statistics[ix][1]
        std_merrs[k] = fit_statistics[ix][2]

    x, y, sigma_y = data
    if isinstance(data_occ,np.ndarray):
        x_occ, y_occ, sigma_y_occ = data_occ
    if not isinstance(data_occ,np.ndarray):
        returndict = {
            'fittype':'precession_fit_k2p_params',
            'fitinfo':{
                'initial_guess':theta_maxlike,
                'maxlikeparams':theta_maxlike,
                'medianparams':medianparams,
                'std_perrs':std_perrs,
                'std_merrs':std_merrs
            },
            'samplesavpath':samplesavpath,
            'data':{
                'epoch':x,
                'tmid_minus_offset':y,
                'err_tmid':sigma_y,
            },
        }
    elif isinstance(data_occ,np.ndarray):
        returndict = {
            'fittype':'precession_fit_k2p_params',
            'fitinfo':{
                'initial_guess':theta_maxlike,
                'maxlikeparams':theta_maxlike,
                'medianparams':medianparams,
                'std_perrs':std_perrs,
                'std_merrs':std_merrs
            },
            'samplesavpath':samplesavpath,
            'data':{
                'epoch':x,
                'tmid_minus_offset':y,
                'err_tmid':sigma_y,
                'epoch_occ':x_occ,
                'tocc_minus_offset_occ':y_occ,
                'err_tmid_occ':sigma_y_occ,
            },
        }

    if plotcorner:
        if not plotdir:
            plotdir = os.path.join('../results/model_comparison_3plus1/',plname)
        cornersavpath = os.path.join(
            plotdir, 'corner_precession_fit_k2p_params{}.png'.format(savstr)
        )

        fig = corner.corner(
            samples,
            labels=fitparamnames,
            truths=theta_maxlike,
            quantiles=[0.16, 0.5, 0.84], show_titles=True
        )

        fig.savefig(cornersavpath, dpi=300)
        if verbose:
            LOGINFO('saved {:s}'.format(cornersavpath))

    return returndict



#################################
# main model comparison routine #
#################################
def main(plname, max_n_steps=10, overwrite=0, Mstar=None, Rstar=None, Mplanet=None,
         Rplanet=None, abyRstar_perr=None, abyRstar_merr=None, a_perr=None,
         a_merr=None, Rp_perr=None, Rp_merr=None, max_n_steps_prec=10,
         use_manual_precession=False,
         sampledir='/home/luke/local/emcee_chains/', run_precession_model=True,
         transitpath=None, occpath=None):
    '''
    Compare linear, quadratic, and apsidal precession models. If precession
    data is found, at
        '../data/{:s}_occultation_times_selected.csv'.format(plname)
    it will be used.

    args:
        plname (str): planet name, used to retrieve data.

    kwargs (all optional):
        Mstar, Rstar, Mplanet (float): units of Msun, Rsun, Mjup.
    '''

    if not transitpath:
        transitpath = (
            '../data/{:s}_literature_and_TESS_times_O-C_vs_epoch_selected.csv'
            .format(plname)
        )
    if not occpath:
        occpath = (
            '../data/{:s}_occultation_times_selected.csv'
            .format(plname)
        )

    savdir = '../results/model_comparison_3plus1/'+plname+'/'
    if not os.path.exists(savdir):
        os.mkdir(savdir)

    print('getting data from {:s}'.format(transitpath))
    x, y, sigma_y, data, tcol, _ = get_data(datacsv=transitpath)

    ylabel = '('+tcol.replace('_',' ')+')*24*60 [min]'
    initial_plot_data(x, y, sigma_y, savpath=savdir+'data.png', xlabel='epoch',
                      ylabel=ylabel)

    # optionally, include occultation data, as well as timing data.
    x_occ, y_occ, sigma_y_occ, data_occ, occ_tcol = None,None,None,None,None
    if os.path.exists(occpath):
        print('getting data from {:s}'.format(occpath))
        x_occ, y_occ, sigma_y_occ, data_occ, occ_tcol, _ = (
            get_data(datacsv=occpath, is_occultation=True)
        )

    # Look at maximum likelihood models for linear, quadratic, and precession
    # cases.
    theta_linear = best_theta(1, data, data_occ=data_occ)
    theta_quadratic = best_theta(2, data, data_occ=data_occ)

    # precession model optimization is TRICKIER. exploring the max likelihood
    # surface this way doesn't seem to converge!

    #NOTE: when adding new times, want theta_linear[0] to set the guess. one
    #manual iteration is necessary.
    if run_precession_model:
        if plname=='WASP-4b':
            init_theta_precession = ( np.array(
                [1158502.0451, 1.33823129*24*60, 1e-3, 2.4, 1.49, 1.321, 0.0226])
            )
            #if impose_k2p_physical:
            #    init_theta_precession = ( np.array(
            #        [1.15850293e+06, 1927.0532, 1e-3, 5., 0.7, 1.321, 0.0226])
            #    )
            #else:
            #    init_theta_precession = ( np.array(
            #        [1.15850293e+06, 1927.0532, 1e-3, 5., 1.5, 1.321, 0.0226])
            #    )
        else:
            raise NotImplementedError

        if use_manual_precession:
            print('WRN! using manual precession initialization values to start MCMC')
            print('\nWRN! using initial guess...')
            theta_maxlike_precession = init_theta_precession

        # precession_result = ml_precession(data, data_occ=data_occ,
        #                                   init_theta=init_theta_precession)

        # if precession_result.success and not use_manual_precession:
        #     print('SUCCESS! tricked numerical optimization to get precession rsult')
        #     print(precession_result)
        #     theta_maxlike_precession = precession_result.x
        # else:
        #     print('WRN! using manual precession initialization values to start MCMC')
        #     print(precession_result.message)
        #     print('\nWRN! using initial guess...')
        #     theta_maxlike_precession = init_theta_precession
    else:
        raise NotImplementedError

    plot_maxlikelihood_models(x, y, sigma_y, theta_linear, theta_quadratic,
                              savpath=os.path.join(savdir,'data_maxlikelihood_fits.png'),
                              xlabel='epoch', ylabel=ylabel)

    plot_maxlikelihood_OminusC(x, y, sigma_y, theta_linear, theta_quadratic,
                               theta_maxlike_precession,
                               savpath=os.path.join(savdir,'data_maxlikelihood_OminusC.png'),
                               xlabel='epoch',
                               ylabel='deviation from constant period [min]',
                               legendstr='max likelihood',
                               x_occ=x_occ, y_occ=y_occ,
                               sigma_y_occ=sigma_y_occ)

    #########################################
    print('-----frequentist approach-----\n')
    #########################################
    # Frequentist approach: treat the linear model as the null hypothesis. Ask:
    # is there enough evidence to justify a more complicated quadratic model?
    # Answer by comparing the observed chi^2 difference to its expected
    # distribution,
    #    f(x, df) = \frac{1}{(2 \gamma(df/2)} (x/2)^{df/2-1} \exp(-x/2).
    # (See docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2.html)

    _, AIC_linear, BIC_linear = chi2_maxlike(1, data, data_occ=data_occ)
    _, AIC_quad, BIC_quad = chi2_maxlike(2, data, data_occ=data_occ)
    if run_precession_model:
        _, AIC_prec, BIC_prec = chi2_bestfit_precession(
            data, theta_maxlike_precession, data_occ=data_occ)

    p_value = plot_chi2_diff_distribution_comparison(
        data, data_occ=data_occ,
        savpath=os.path.join(savdir,'chi2_diff_distribution_comparison.png'))

    print('-----linear vs quad-----')
    print('p_value for ruling out the linear model: {:.3e}'.format(p_value))
    print('delta_AIC = AIC_linear-AIC_quad = {:.2f}'.format(AIC_linear-AIC_quad))
    print('delta_BIC = BIC_linear-BIC_quad = {:.2f}'.format(BIC_linear-BIC_quad))
    print('approx Bayes Factor = exp(deltaBIC/2) = {:.2e}'.
          format(np.exp(BIC_linear-BIC_quad)/2))

    if run_precession_model:
        print('-----quad vs MAX-LIKELIHOOD precession-----')
        print('delta_AIC = AIC_prec-AIC_quad = {:.2f}'.format(AIC_prec-AIC_quad))
        print('delta_BIC = BIC_prec-BIC_quad = {:.2f}'.format(BIC_prec-BIC_quad))
        print('approx Bayes Factor = exp(deltaBIC/2) = {:.2e}'.
              format(np.exp(BIC_prec-BIC_quad)/2))
        print('see Kass & Raftery 1995 for interpretation')

    # Before diving into Bayesian model comparison, we need to do the Bayesian
    # model fitting. What are the best-fitting model parameters for each model?
    # To answer, you must set priors. To set priors, you need to get planet
    # parameters. Get them from TEPCAT.
    if (not Mstar) and (not Rstar) and (not Mplanet):
        raise NotImplementedError
    else:
        Mstar = float(Mstar)*u.Msun
        Rstar = float(Rstar)*u.Rsun
        Mplanet = float(Mplanet)*u.Mjup

    nominal_period = theta_linear[1]*u.minute
    semimaj = ( ( nominal_period**2 *
               const.G * (Mstar+Mplanet) / (4*np.pi**2) )**(1/3) ).to(u.Rsun)
    nominal_t0 = theta_linear[0]*u.minute

    plparams = Rstar, Mplanet, Mstar, semimaj, nominal_period, nominal_t0

    ###################################################
    print('\n-----max-likelihood chi2 solution-----\n')
    ###################################################

    print('quadratic (decay) model maxlike parameters\n')

    dP_dt = 2 * theta_quadratic[2] / theta_quadratic[1]
    print('dP/dt = {:.3e} = {:.1f} millisec/yr'.
          format(dP_dt, dP_dt/(u.millisecond/u.yr).cgs.scale))

    P_by_dP_dt = ((theta_quadratic[1]*u.minute)/dP_dt).to(u.Myr)
    print('P/(dP/dt) ~= time remaining until DESTRUCTION = = {:.1f}'.
          format(P_by_dP_dt))

    Mp_by_Mstar = (Mplanet/Mstar).cgs.value
    Rstar_by_a = (Rstar/semimaj).cgs.value
    print('Mp/Mstar = {:.1e}, a/Rstar = {:.3f}'.
          format(Mp_by_Mstar, 1/Rstar_by_a))

    Qstar = (
        - 1/dP_dt * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a**5
    )
    print('rough implied Qstar ~= {:.1e}'.format(Qstar))
    print('WRN! use consistent set of planet parameters in final analysis!')

    ##########

    if run_precession_model:
        print('\nprecession model maxlike parameters\n')
        print('t0 [min] = {:.4f}'.format(theta_maxlike_precession[0]))
        print('P [day] = {:.9f}'.format(theta_maxlike_precession[1]/(24*60)))
        print('e = {:.3e}'.format(theta_maxlike_precession[2]))
        print('omega0 = {:.2f}'.format(theta_maxlike_precession[3]))
        print('k2p = {:.3e}'.format(theta_maxlike_precession[4]))
        print('Rplanet = {:.3e}'.format(theta_maxlike_precession[5]))
        print('semimaj = {:.3e}'.format(theta_maxlike_precession[6]))


    ########################################
    print('\n-----bayesian approach-----\n')
    ########################################
    # Bayesian approach: compute the _odds ratios_ between the two models:
    # 
    #   OR(M_1,M_2) = P(M_2 | D) / P(M_1 | D)
    #               = P(D | M_2) P(M_2) / (P(D | M_1) P(M_1)).
    #
    # Take the prior odds ratio, P(M_2)/P(M_1), to be = 1.
    # 
    # We then want the ratio of marginal model likelihoods, AKA the Bayes
    # factor:
    #
    #       bayes factor = P(D | M_2) / P(D | M_1).
    # 
    # We can compute it by noting:
    #
    #   P(D|M) = int_{Θ} P(D|θ,M) P(θ|M) dθ,
    #
    # by the definition of conditional probabilities. This can be
    # computationally intensive, but these models have not many parameters.

    fit_2d = compute_mcmc(1, data, plparams, theta_linear, plname,
                          data_occ=data_occ,
                          overwriteexistingsamples=overwrite,
                          sampledir=sampledir, nworkers=16,
                          max_n_steps=max_n_steps, plotdir=savdir)

    fit_3d = compute_mcmc(2, data, plparams, theta_quadratic, plname,
                          data_occ=data_occ,
                          overwriteexistingsamples=overwrite,
                          sampledir=sampledir, nworkers=16,
                          max_n_steps=max_n_steps,
                          eps=[1e-5, 1e-5, 1e-5], plotdir=savdir)

    if run_precession_model:
        plparams_prec = (
            Rstar, Mplanet, Mstar, semimaj, theta_maxlike_precession[1]*u.min,
            theta_maxlike_precession[0]*u.min
        )

        #FIXME: u need to implement the two new parameters here. (follow
        #notes!)
        fit_prec_wide_prior = compute_mcmc_precession(
            data, plparams_prec, theta_maxlike_precession, plname,
            data_occ=data_occ,
            max_n_steps=max_n_steps_prec, sampledir=sampledir,
            overwriteexistingsamples=overwrite, nworkers=16,
            verbose=True, eps=[1e-5, 1e-5, 1e-3, 1, 1e-3, 1e-2, 1e-4], plotdir=savdir,
            impose_k2p_physical=False)

        # physical let's go!
        fit_prec_phys_prior = compute_mcmc_precession(
            data, plparams_prec, theta_maxlike_precession, plname,
            data_occ=data_occ,
            max_n_steps=max_n_steps_prec, sampledir=sampledir,
            overwriteexistingsamples=overwrite, nworkers=16,
            verbose=True, eps=[1e-5, 1e-5, 1e-3, 1, 1e-3, 1e-2, 1e-4], plotdir=savdir,
            impose_k2p_physical=True)

    else:
        raise NotImplementedError

    for fit, pklsavpath in zip(
        [fit_2d, fit_3d, fit_prec_wide_prior, fit_prec_phys_prior],
        [savdir+'fit_2d.pkl',savdir+'fit_3d.pkl',
         savdir+'fit_prec_wide_prior.pkl',savdir+'fit_prec_phys_prior.pkl']
    ):
        if isinstance(fit, dict):
            with open(pklsavpath, 'wb') as f:
                pickle.dump(fit, f, pickle.HIGHEST_PROTOCOL)
                print('saved {:s}'.format(pklsavpath))

    fi2d = fit_2d['fitinfo']
    fi3d = fit_3d['fitinfo']
    if run_precession_model:
        fiprec_wp = fit_prec_wide_prior['fitinfo']
        fiprec_pp = fit_prec_phys_prior['fitinfo']

    median_t0_2d = fi2d['medianparams']['t0 [min]']
    median_period_2d = fi2d['medianparams']['P [min]']

    median_t0_3d = fi3d['medianparams']['t0 [min]']
    median_period_3d = fi3d['medianparams']['P [min]']
    median_quadterm_3d = fi3d['medianparams']['0.5 dP/dE [min]']

    # get offset needed to convert to BJD_TDB
    t_offset = (
        search('sel_transit_times_BJD_TDB_minus_{:d}_minutes',tcol).fixed[0]
    )

    ##########
    print('\nlinear model best fit parameters\n')
    print('t0 [min] = {:.4f} +({:.4f}), -({:.4f})'.
          format(median_t0_2d,
                 fi2d['std_perrs']['t0 [min]'],
                 fi2d['std_merrs']['t0 [min]'])
    )
    print('t0 [BJD_TDB] = {:.6f} +({:.6f}), -({:.6f})'.
          format(median_t0_2d/(24*60) + t_offset,
                 fi2d['std_perrs']['t0 [min]']/(24*60) ,
                 fi2d['std_merrs']['t0 [min]']/(24*60) )
    )
    print('P [day] = {:.9f} +({:.9f}), -({:.9f})'.
          format(median_period_2d/(24*60),
                 fi2d['std_perrs']['P [min]']/(24*60),
                 fi2d['std_merrs']['P [min]']/(24*60))
    )

    ##########
    print('\nquadratic model best fit parameters\n')
    print('t0 [min] = {:.4f} +({:.4f}), -({:.4f})'.
          format(median_t0_3d,
                 fi3d['std_perrs']['t0 [min]'],
                 fi3d['std_merrs']['t0 [min]'])
    )
    print('t0 [BJD_TDB] = {:.6f} +({:.6f}), -({:.6f})'.
          format(median_t0_3d/(24*60) + t_offset,
                 fi3d['std_perrs']['t0 [min]']/(24*60) ,
                 fi3d['std_merrs']['t0 [min]']/(24*60) )
    )
    print('P [day] = {:.9f} +({:.9f}), -({:.9f})'.
          format(median_period_3d/(24*60),
                 fi3d['std_perrs']['P [min]']/(24*60),
                 fi3d['std_merrs']['P [min]']/(24*60))
    )
    print('0.5 dP/dE [min] = {:.4e} +({:.4e}), -({:.4e})'.
          format(median_quadterm_3d,
                 fi3d['std_perrs']['0.5 dP/dE [min]'],
                 fi3d['std_merrs']['0.5 dP/dE [min]'])
    )

    dP_dt = (
        2 * median_quadterm_3d
        /
        median_period_3d
    )
    dP_dt_upper = (
        2 * (fi3d['medianparams']['0.5 dP/dE [min]'] +
             fi3d['std_perrs']['0.5 dP/dE [min]'])
        /
        fi3d['medianparams']['P [min]']
    )
    dP_dt_lower = (
        2 * (fi3d['medianparams']['0.5 dP/dE [min]'] -
             fi3d['std_merrs']['0.5 dP/dE [min]'])
        /
        fi3d['medianparams']['P [min]']
    )
    print('dP/dt = {:.3e} = {:.1f} millisec/yr'.
          format(dP_dt, dP_dt/(u.millisecond/u.yr).cgs.scale))
    print('(dP/dt)_upper = {:.3e} = {:.1f} millisec/yr'.
          format(dP_dt_upper, dP_dt_upper/(u.millisecond/u.yr).cgs.scale))
    print('(dP/dt)_lower = {:.3e} = {:.1f} millisec/yr'.
          format(dP_dt_lower, dP_dt_lower/(u.millisecond/u.yr).cgs.scale))
    print('-> dP/dt = {:.3e} +({:.3e}) -({:.3e})'.format(
        dP_dt,
        (dP_dt_upper-dP_dt),
        (dP_dt-dP_dt_lower)
    ))
    print('-> dP/dt = {:.2f} +({:.2f}) -({:.2f}) millisec/yr'.format(
        dP_dt/(u.millisecond/u.yr).cgs.scale,
        (dP_dt_upper-dP_dt)/(u.millisecond/u.yr).cgs.scale,
        (dP_dt-dP_dt_lower)/(u.millisecond/u.yr).cgs.scale
    ))

    P_by_dP_dt = ((fi3d['medianparams']['P [min]']*u.minute)/dP_dt).to(u.Myr)
    print('P/(dP/dt) ~= time remaining until DESTRUCTION = = {:.1f}'.
          format(P_by_dP_dt))

    Mp_by_Mstar = (Mplanet/Mstar).cgs.value
    Rstar_by_a = (Rstar/semimaj).cgs.value
    if isinstance(abyRstar_perr,float) and isinstance(abyRstar_merr,float):
        abyRstar = 1/Rstar_by_a
        abyRstar_upper = abyRstar + abyRstar_perr
        abyRstar_lower = abyRstar - abyRstar_merr
        Rstar_by_a_upper = 1/abyRstar_lower
        Rstar_by_a_lower = 1/abyRstar_upper
    else:
        Rstar_by_a_upper = Rstar_by_a
        Rstar_by_a_lower = Rstar_by_a

    print('Mp/Mstar = {:.1e}, a/Rstar = {:.3f}'.
          format(Mp_by_Mstar, 1/Rstar_by_a))
    print('(Rstar/a)_upper = {:.4f}, (Rstar/a)_lower = {:.4f}'.
          format(Rstar_by_a_upper, Rstar_by_a_lower))

    Qstar = (
        - 1/dP_dt * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a**5
    )
    Qstar_upper = (
        - 1/dP_dt_upper * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a_upper**5
    )
    Qstar_lower = (
        - 1/dP_dt_lower * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a_lower**5
    )
    print('implied Qstar = {:.1e}'.format(Qstar))
    print('implied Qstar_upper = {:.1e}'.format(Qstar_upper))
    print('implied Qstar_lower = {:.1e}'.format(Qstar_lower))

    print('WRN: could propagate uncertainties consistently for Qstar errs '
          '(by including sigma_period, along with sigma_quad)')

    print('\nquadratic model upper limits\n')
    onesigma_lower = fi3d['onesigma_lower']
    twosigma_lower = fi3d['twosigma_lower']
    threesigma_lower = fi3d['threesigma_lower']
    onesigma_upper = fi3d['onesigma_upper']
    twosigma_upper = fi3d['twosigma_upper']
    threesigma_upper = fi3d['threesigma_upper']

    for ix, l in enumerate([
        onesigma_lower['0.5 dP/dE [min]'],
        twosigma_lower['0.5 dP/dE [min]'],
        threesigma_lower['0.5 dP/dE [min]']
    ]):
        print('0.5 dE/dt > {:.3e} at {} sigma'.format(l, ix+1))
    for ix, l in enumerate([
        onesigma_upper['0.5 dP/dE [min]'],
        twosigma_upper['0.5 dP/dE [min]'],
        threesigma_upper['0.5 dP/dE [min]']
    ]):
        print('0.5 dE/dt < {:.3e} at {} sigma'.format(l, ix+1))

    onesigma_lower_dP_dt = (
        2 * onesigma_lower['0.5 dP/dE [min]']
        /
        median_period_3d
    )
    twosigma_lower_dP_dt = (
        2 * twosigma_lower['0.5 dP/dE [min]']
        /
        median_period_3d
    )
    threesigma_lower_dP_dt = (
        2 * threesigma_lower['0.5 dP/dE [min]']
        /
        median_period_3d
    )
    onesigma_upper_dP_dt = (
        2 * onesigma_upper['0.5 dP/dE [min]']
        /
        median_period_3d
    )
    twosigma_upper_dP_dt = (
        2 * twosigma_upper['0.5 dP/dE [min]']
        /
        median_period_3d
    )
    threesigma_upper_dP_dt = (
        2 * threesigma_upper['0.5 dP/dE [min]']
        /
        median_period_3d
    )

    print('dP/dt > {:.3e} millisec/yr at 1 sigma'.format(onesigma_lower_dP_dt/(u.millisecond/u.yr).cgs.scale))
    print('dP/dt > {:.3e} millisec/yr at 2 sigma'.format(twosigma_lower_dP_dt/(u.millisecond/u.yr).cgs.scale))
    print('dP/dt > {:.3e} millisec/yr at 3 sigma'.format(threesigma_lower_dP_dt/(u.millisecond/u.yr).cgs.scale))

    print('dP/dt < {:.3e} millisec/yr at 1 sigma'.format(onesigma_upper_dP_dt/(u.millisecond/u.yr).cgs.scale))
    print('dP/dt < {:.3e} millisec/yr at 2 sigma'.format(twosigma_upper_dP_dt/(u.millisecond/u.yr).cgs.scale))
    print('dP/dt < {:.3e} millisec/yr at 3 sigma'.format(threesigma_upper_dP_dt/(u.millisecond/u.yr).cgs.scale))

    onesigma_lower_Qstar = (
        - 1/onesigma_lower_dP_dt * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a**5
    )
    twosigma_lower_Qstar = (
        - 1/twosigma_lower_dP_dt * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a**5
    )
    threesigma_lower_Qstar = (
        - 1/threesigma_lower_dP_dt * 27*np.pi/2 *  Mp_by_Mstar * Rstar_by_a**5
    )

    print('(median a/Rstar) Qstar > {:.3e} at 1 sigma'.format(onesigma_lower_Qstar))
    print('(median a/Rstar) Qstar > {:.3e} at 2 sigma'.format(twosigma_lower_Qstar))
    print('(median a/Rstar) Qstar > {:.3e} at 3 sigma'.format(threesigma_lower_Qstar))


    ##########
    # PRECESSION MODEL MEDIAN (BEST-FIT) PARAMETERS
    if run_precession_model:
        for fiprec, substr in zip([fiprec_wp, fiprec_pp],
                                  ['WIDE ','PHYSICAL ']
        ):
            median_t0_prec = fiprec['medianparams']['t0 [min]']
            median_Ps_prec = fiprec['medianparams']['P_side [min]']
            median_e_prec = fiprec['medianparams']['e']
            median_omega0_prec = fiprec['medianparams']['omega0']
            median_k2p_prec = fiprec['medianparams']['k2p']
            median_Rp_prec = fiprec['medianparams']['Rp']
            median_a_prec = fiprec['medianparams']['a']

            print('\n{}precession model best fit parameters\n'.format(substr))
            print('t0 [min] = {:.4f} +({:.4f}), -({:.4f})'.
                  format(median_t0_prec,
                         fiprec['std_perrs']['t0 [min]'],
                         fiprec['std_merrs']['t0 [min]'])
            )
            print('t0 [BJD_TDB] = {:.5f} +({:.5f}), -({:.5f})'.
                  format(median_t0_prec/(24*60) + t_offset,
                         fiprec['std_perrs']['t0 [min]']/(24*60) ,
                         fiprec['std_merrs']['t0 [min]']/(24*60) )
            )
            print('P [day] = {:.8f} +({:.8f}), -({:.8f})'.
                  format(median_Ps_prec/(24*60),
                         fiprec['std_perrs']['P_side [min]']/(24*60),
                         fiprec['std_merrs']['P_side [min]']/(24*60))
            )
            print('e = {:.3e} +({:.3e}), -({:.3e})'.
                  format(median_e_prec,
                         fiprec['std_perrs']['e'],
                         fiprec['std_merrs']['e'])
            )
            print('e = {:.5f} +({:.5f}), -({:.5f})'.
                  format(median_e_prec,
                         fiprec['std_perrs']['e'],
                         fiprec['std_merrs']['e'])
            )
            print('omega0 = {:.2f} +({:.2f}), -({:.2f})'.
                  format(median_omega0_prec,
                         fiprec['std_perrs']['omega0'],
                         fiprec['std_merrs']['omega0'])
            )
            print('k2p = {:.3f} +({:.3f}), -({:.3f})'.
                  format(median_k2p_prec,
                         fiprec['std_perrs']['k2p'],
                         fiprec['std_merrs']['k2p'])
            )
            print('Rp = {:.3f} +({:.3f}), -({:.3f})'.
                  format(median_Rp_prec,
                         fiprec['std_perrs']['Rp'],
                         fiprec['std_merrs']['Rp'])
            )
            print('a = {:.3f} +({:.3f}), -({:.3f})'.
                  format(median_a_prec,
                         fiprec['std_perrs']['a'],
                         fiprec['std_merrs']['a'])
            )

            # implies maximum timing variation away from P/2 of...? Use Eq 33
            # of Winn et al 2010.
            orbital_period = median_period_2d/(24*60)

            max_secondary_variation = (
                orbital_period/2 * (4/np.pi)*median_e_prec
            )*u.day
            max_secondary_variation_upper = (
                orbital_period/2 *
                (4/np.pi)*(median_e_prec+fiprec['std_perrs']['e'])
            )*u.day
            max_secondary_variation_lower = (
                orbital_period/2 *
                (4/np.pi)*(median_e_prec-fiprec['std_merrs']['e'])
            )*u.day
            print('implied amplitude of occultation timing variation away '
                  'from P/2: {:.1f} +({:.1f}) -({:.1f})'.
                 format(max_secondary_variation.to(u.minute),
                        max_secondary_variation_upper.to(u.minute),
                        max_secondary_variation_lower.to(u.minute)))

            # implies domega/dt of what? Use Eq 16 of Patra+ 2017, which i checked
            # in 20190309_checking_k2_eqn.pdf :
            # k2,p = (1/(15*pi))  domega/dE   (Mp/Mstar) (a/Rp)^5
            # or rearrange :
            # domega/dE = 15pi * k2p  (Mstar/Mp) (Rp/a)^5.
            # and
            # domega_dt = 1/P * domega_dE
            Mp_by_Mstar = (Mplanet/Mstar).cgs.value

            median_Rplanet_by_a = (median_Rp_prec*u.Rjup/
                                   (median_a_prec*u.AU)).cgs.value

            upper_k2p_prec = median_k2p_prec + fiprec['std_perrs']['k2p']
            lower_k2p_prec = median_k2p_prec - fiprec['std_merrs']['k2p']

            upper_Rplanet_by_a = (
                ((median_Rp_prec + fiprec['std_perrs']['Rp'])*u.Rjup
                /
                ((median_a_prec - fiprec['std_merrs']['a'])*u.AU)).cgs.value
            )
            lower_Rplanet_by_a = (
                ((median_Rp_prec - fiprec['std_merrs']['Rp'])*u.Rjup
                /
                ((median_a_prec + fiprec['std_perrs']['a'])*u.AU)).cgs.value
            )

            median_domega_dE_prec = (
                15*np.pi * median_k2p_prec * (1/Mp_by_Mstar) *
                median_Rplanet_by_a**5
            )
            upper_domega_dE_prec = (
                15*np.pi * upper_k2p_prec * (1/Mp_by_Mstar) *
                upper_Rplanet_by_a**5
            )
            lower_domega_dE_prec = (
                15*np.pi * lower_k2p_prec * (1/Mp_by_Mstar) *
                lower_Rplanet_by_a**5
            )

            period_yr = median_Ps_prec/(24*60*365.2425)
            domega_dt_in_deg_per_year = (
                (((1/period_yr)*median_domega_dE_prec)*u.rad).to(u.deg).value
            )
            domega_dt_in_deg_per_year_perr = (
                (((1/period_yr)*(upper_domega_dE_prec-median_domega_dE_prec))*u.rad).to(u.deg).value
            )
            domega_dt_in_deg_per_year_merr = (
                (((1/period_yr)*(median_domega_dE_prec-lower_domega_dE_prec))*u.rad).to(u.deg).value
            )
            print('in deg/year, domega_dt = {:.2f} +({:.2f}), -({:.2f})'.
                  format(domega_dt_in_deg_per_year,
                         domega_dt_in_deg_per_year_perr,
                         domega_dt_in_deg_per_year_merr)
            )
            print('implying precession period {:.1f} years +({:.1f}) -({:.1f})'.
                  format(
                      360/domega_dt_in_deg_per_year,
                      360/(domega_dt_in_deg_per_year - np.abs(domega_dt_in_deg_per_year_merr)),
                      360/(domega_dt_in_deg_per_year + domega_dt_in_deg_per_year_perr)
                  )
            )

            ##########
            # print('\nprecession model maxlike parameters\n')
            # print('t0 [min] = {:.4f}'.
            #       format(theta_maxlike_precession[0])
            # )
            # print('P [day] = {:.9f}'.
            #       format(theta_maxlike_precession[1]/(24*60))
            # )
            # print('e = {:.3e}'.
            #       format(theta_maxlike_precession[2])
            # )
            # print('omega0 = {:.2f}'.
            #       format(theta_maxlike_precession[3])
            # )
            # print('domega_dE = {:.3e}'.
            #       format(theta_maxlike_precession[4])
            # )
            # # domega_dt = 1/P * domega_dE
            # period_yr = theta_maxlike_precession[1]/(24*60*365.2425)
            # domega_dt_in_deg_per_year = (
            #     (((1/period_yr)*theta_maxlike_precession[4])*u.rad).to(u.deg).value
            # )
            # print('in deg/year, domega_dt = {:.2f}'.
            #       format(domega_dt_in_deg_per_year)
            # )
            # print('implying precession period {:.1f} years'.
            #       format(360/domega_dt_in_deg_per_year))

            if fiprec==fiprec_wp:
                theta_bestfit_prec_wp = np.array([median_t0_prec, median_Ps_prec,
                                         median_e_prec, median_omega0_prec,
                                         median_k2p_prec, median_Rp_prec,
                                         median_a_prec ])
            else:
                theta_bestfit_prec_pp = np.array([median_t0_prec, median_Ps_prec,
                                         median_e_prec, median_omega0_prec,
                                         median_k2p_prec, median_Rp_prec,
                                         median_a_prec ])

    ##########################################
    # check if these values are at all a good fit to the data!
    theta_bestfit_linear = [median_t0_2d, median_period_2d]
    theta_bestfit_quad = [median_t0_3d, median_period_3d, median_quadterm_3d]
    for savstr, theta_bestfit_prec in zip(
        ['wideprior','physicalprior'],
        [theta_bestfit_prec_wp,theta_bestfit_prec_pp]
    ):
        plot_maxlikelihood_OminusC(x, y, sigma_y, theta_bestfit_linear,
                                   theta_bestfit_quad, theta_bestfit_prec,
                                   savpath=os.path.join(savdir,'data_bestfit_OminusC_{}.png'.format(savstr)),
                                   xlabel='epoch',
                                   ylabel='deviation from constant period [min]',
                                   legendstr='median MCMC',
                                   x_occ=x_occ, y_occ=y_occ,
                                   sigma_y_occ=sigma_y_occ)

    ########################################
    # chi2 values for best fit parameters. #
    ########################################
    print('\n-----chi2 values for best fit parameters-----\n')
    _, AIC_linear, BIC_linear = (
        chi2_bestfit_posterior(1, data, theta_bestfit_linear, data_occ=data_occ)
    )
    _, AIC_quad, BIC_quad = (
        chi2_bestfit_posterior(2, data, theta_bestfit_quad, data_occ=data_occ)
    )
    if run_precession_model:
        _, AIC_prec_wp, BIC_prec_wp = (
            chi2_bestfit_precession(data, theta_bestfit_prec_wp, data_occ=data_occ)
        )
        _, AIC_prec_pp, BIC_prec_pp = (
            chi2_bestfit_precession(data, theta_bestfit_prec_pp, data_occ=data_occ)
        )

    print('-----linear vs quad-----')
    print('delta_AIC = AIC_linear-AIC_quad = {:.2f}'.format(AIC_linear-AIC_quad))
    print('delta_BIC = BIC_linear-BIC_quad = {:.2f}'.format(BIC_linear-BIC_quad))
    print('approx Bayes Factor = exp(deltaBIC/2) = {:.2e}'.
          format(np.exp(BIC_linear-BIC_quad)/2))

    if run_precession_model:
        print('-----quad vs precession (WIDE PRIOR)-----')
        print('delta_AIC = AIC_prec-AIC_quad = {:.2f}'.format(AIC_prec_wp-AIC_quad))
        print('delta_BIC = BIC_prec-BIC_quad = {:.2f}'.format(BIC_prec_wp-BIC_quad))
        print('approx Bayes Factor = exp(deltaBIC/2) = {:.2e}'.
              format(np.exp(BIC_prec_wp-BIC_quad)/2))
        print('see Kass & Raftery 1995 for interpretation')

        print('-----quad vs precession (PHYSICAL PRIOR)-----')
        print('delta_AIC = AIC_prec-AIC_quad = {:.2f}'.format(AIC_prec_pp-AIC_quad))
        print('delta_BIC = BIC_prec-BIC_quad = {:.2f}'.format(BIC_prec_pp-BIC_quad))
        print('approx Bayes Factor = exp(deltaBIC/2) = {:.2e}'.
              format(np.exp(BIC_prec_pp-BIC_quad)/2))
        print('see Kass & Raftery 1995 for interpretation')
    # NOTE: If you wanted to compute proper Bayes factors, you would need to do
    # a big integral for the evidence. Skip this.


def get_plmass_given_K(a, Mstar, sini, K, e=0):
    # Lovis and Fischer, eq 12.
    Mp = K * (const.G/(1-e**2))**(-1/2) * sini**(-1) * Mstar**(1/2) * a**(1/2)

    return Mp.to(u.Mjup)


if __name__ == "__main__":

    ######################
    # CHANGED MOST OFTEN #
    ######################
    max_n_steps = 5000
    max_n_steps_prec = 40000
    use_manual_precession = 1

    ######################
    # CHANGED LESS OFTEN #
    ######################
    plname = 'WASP-4b' # only one for this model set
    overwrite = 1 # fixed to overwrite (unless i learn to emcee better.)
    transitpath = None
    occpath = None
    sampledir='/home/luke/local/emcee_chains/'
    abyRstar_perr, abyRstar_merr = None, None
    a_perr, a_merr, Rp_perr, Rp_merr = None, None, None, None

    if plname == 'WASP-4b':
        Mstar, Rstar, Mplanet, Rplanet = 0.864, 0.893, 1.186, 1.321 # USED: my table 1
        run_precession_model = True
        transitpath = '../data/WASP-4b_literature_and_TESS_times_O-C_vs_epoch_selected.csv'
        sampledir='/home/luke/local/emcee_chains/'
        abyRstar_perr, abyRstar_merr = 0.023, 0.052 # table 1.
        a_perr, a_merr = 0.0007, 0.0008 # AU
        Rp_perr, Rp_merr = 0.039, 0.039 # RJup

    #################
    # CHANGED LEAST #
    #################
    np.random.seed(42)
    main(plname, max_n_steps=max_n_steps, overwrite=overwrite, Mstar=Mstar,
         Rstar=Rstar, Mplanet=Mplanet, Rplanet=Rplanet,
         abyRstar_perr=abyRstar_perr, abyRstar_merr=abyRstar_merr,
         a_perr=a_perr, a_merr=a_merr, Rp_perr=Rp_perr, Rp_merr=Rp_merr,
         max_n_steps_prec=max_n_steps_prec,
         use_manual_precession=use_manual_precession,
         run_precession_model=run_precession_model,
         transitpath=transitpath, occpath=occpath,
         sampledir=sampledir)
