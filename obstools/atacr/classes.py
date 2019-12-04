# Copyright 2019 Pascal Audet & Helen Janiszewski
#
# This file is part of OBStools.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""

:mod:`~obstools.atacr` defines the following base classes:

- :class:`~obstools.atacr.classes.DayNoise`
- :class:`~obstools.atacr.classes.StaNoise`
- :class:`~obstools.atacr.classes.TFNoise`
- :class:`~obstools.atacr.classes.EventStream`

The class :class:`~obstools.atacr.classes.DayNoise` contains attributes
and methods for the analysis of two- to four-component day-long time-series
(3-component seismograms and pressure data). Objects created with this class
are required in any subsequent analysis. The available methods calculate the
power-spectral density (psd) function of sub-windows and identifies windows
with anomalous psd properties. These windows are flagged as 'bad' and are excluded
from the final averages of all possible Fourier power spectra and cross spectra
across all available components.

The class :class:`~obstools.atacr.classes.StaNoise` contains attributes
and methods for the aggregation of day-long time series into station
average. An object created with this class requires that objects created with
`DayNoise` are available in memory. Methods available for this calss are
similar to those defined in the `DayNoise` class, but are applied to daily 
spectral averages, as opposed to sub-daily averages. The result is a spectral
average that represents all available data for the specific stations.  

The class :class:`~obstools.atacr.classes.TFNoise` contains attributes
and methods for the calculation of transfer functions from noise
traces used to correct the vertical component. A `TFNoise` object works with 
either one (or both) `DayNoise` and `StaNoise` objects to calculate all possible
transfer functions across all available components. These transfer functions
are saved as attributes of the object in a Dictionary. 

The class :class:`~obstools.atacr.classes.EventStream` contains attributes
and methods for the application of the transfer functions to the
event traces for the correction (cleaning) of vertical component
seismograms. An `EventStream` object is initialized with raw (or pre-processed)
seismic and/or pressure data and needs to be processed using the same (sub) window 
properties as the `DayNoise` objects. This ensures that the component corrections
are safely applied to produce corrected (cleaned) vertical components. 

:mod:`~obstoolsatacr.` further defines the following container classes:

- :class:`~obstools.atacr.classes.Power`
- :class:`~obstools.atacr.classes.Cross`
- :class:`~obstools.atacr.classes.Rotation`

These classes are used as containers for individual traces/objects
that are used as attributes of the base classes. 

"""

from scipy.signal import spectrogram, detrend
from scipy.linalg import norm
import matplotlib.pyplot as plt
import numpy as np
import pickle
from obspy.core import Stream, Trace, read
from obstools.atacr import utils, plot


class Power(object):
    """
    Container for power spectra for each component, with any shape

    Attributes
    ----------
    c11 : :class:`~numpy.ndarray`
        Power spectral density for component 1 (any shape)
    c22 : :class:`~numpy.ndarray`
        Power spectral density for component 2 (any shape)
    cZZ : :class:`~numpy.ndarray`
        Power spectral density for component Z (any shape)
    cPP : :class:`~numpy.ndarray`
        Power spectral density for component P (any shape)
    """
    def __init__(self, c11=None, c22=None, cZZ=None, cPP=None):
        self.c11 = c11
        self.c22 = c22
        self.cZZ = cZZ
        self.cPP = cPP


class Cross(object):
    """
    Container for cross-power spectra for each component pairs, with any shape

    Attributes
    ----------
    c12 : :class:`~numpy.ndarray`
        Cross-power spectral density for components 1 and 2 (any shape)
    c1Z : :class:`~numpy.ndarray`
        Cross-power spectral density for components 1 and Z (any shape)
    c1P : :class:`~numpy.ndarray`
        Cross-power spectral density for components 1 and P (any shape)
    c2Z : :class:`~numpy.ndarray`
        Cross-power spectral density for components 2 and Z (any shape)
    c2P : :class:`~numpy.ndarray`
        Cross-power spectral density for components 2 and P (any shape)
    cZP : :class:`~numpy.ndarray`
        Cross-power spectral density for components Z and P (any shape)
    """
    def __init__(self, c12=None, c1Z=None, c1P=None, c2Z=None, c2P=None, cZP=None):
        self.c12 = c12
        self.c1Z = c1Z
        self.c1P = c1P
        self.c2Z = c2Z
        self.c2P = c2P
        self.cZP = cZP


class Rotation(object):
    """
    Container for rotated spectra, with any shape

    Attributes
    ----------
    cHH : :class:`~numpy.ndarray`
        Power spectral density for rotated horizontal component H (any shape)
    cHZ : :class:`~numpy.ndarray`
        Cross-power spectral density for components H and Z (any shape)
    cHP : :class:`~numpy.ndarray`
        Cross-power spectral density for components H and P (any shape)
    coh : :class:`~numpy.ndarray`
        Coherence between horizontal components
    ph : :class:`~numpy.ndarray`
        Phase of cross-power spectrum between horizontal components
    tilt : float
        Angle (azimuth) of tilt axis
    coh_value : float
        Maximum coherence 
    phase_value : float
        Phase at maximum coherence
    direc : :class:`~numpy.ndarray`
        Directions for which the coherence is calculated

    """
    def __init__(self, cHH=None, cHZ=None, cHP=None, coh=None, ph=None, tilt=None, \
        coh_value=None, phase_value=None, direc=None):

        self.cHH = cHH
        self.cHZ = cHZ
        self.cHP = cHP
        self.coh = coh
        self.ph = ph
        self.tilt = tilt
        self.coh_value = coh_value
        self.phase_value = phase_value
        self.direc = direc


class DayNoise(object):
    """
    A DayNoise object contains attributes that associate
    three-component raw (or deconvolved) traces, metadata information
    and window parameters. The available methods carry out the quality 
    control steps and the average daily spectra for windows flagged as 
    "good". 

    Note
    ----
    The object is initialized with :class:`~obspy.core.Trace` objects for 
    H1, H2, HZ and P components. Traces can be empty if data are not available.
    Upon saving, those traces are discarded to save disk space. 

    Attributes
    ----------
    window : float
        Length of time window in seconds
    overlap : float
        Fraction of overlap between adjacent windows
    key : str
        Station key for current object
    dt : float
        Sampling distance in seconds. Obtained from ``trZ`` object
    npts : int
        Number of points in time series. Obtained from ``trZ`` object
    fs : float
        Sampling frequency (in Hz). Obtained from ``trZ`` object
    year : str
        Year for current object (obtained from UTCDateTime). Obtained from ``trZ`` object
    julday : str
        Julian day for current object (obtained from UTCDateTime). Obtained from ``trZ`` object
    ncomp : int
        Number of available components (either 2, 3 or 4). Obtained from non-empty ``Trace`` objects
    tf_list : Dict
        Dictionary of possible transfer functions given the available components. 
    goodwins : list 
        List of booleans representing whether a window is good (True) or not (False). 
        This attribute is returned from the method :func:`~obstools.atacr.classes.DayNoise.QC_daily_spectra`
    power : :class:`~obstools.atacr.classes.Power`
        Container for daily spectral power for all available components
    cross : :class:`~obstools.atacr.classes.Cross`
        Container for daily cross spectral power for all available components
    rotation : :class:`~obstools.atacr.classes.Rotation`
        Container for daily rotated (cross) spectral power for all available components
    f : :class:`~numpy.ndarray`
        Frequency axis for corresponding time sampling parameters. Determined from method 
        :func:`~obstools.atacr.classes.DayNoise.average_daily_spectra`

    .. note::

        In the examples below, the SAC data were obtained and pre-processed
        using the accompanying script ``atacr_download_data.py``. See the script
        and tutorial for details.

    Example
    -------

    Get demo data

    >>> from obstools.atacr.classes import DayNoise
    >>> daynoise = DayNoise()
    Uploading demo data
    >>> print(*[daynoise.tr1, daynoise.tr2, daynoise.trZ, daynoise.trP], sep="\n") 
    7D.M08A..1 | 2012-03-04T00:00:00.005500Z - 2012-03-04T23:59:59.805500Z | 5.0 Hz, 432000 samples
    7D.M08A..2 | 2012-03-04T00:00:00.005500Z - 2012-03-04T23:59:59.805500Z | 5.0 Hz, 432000 samples
    7D.M08A..P | 2012-03-04T00:00:00.005500Z - 2012-03-04T23:59:59.805500Z | 5.0 Hz, 432000 samples
    7D.M08A..Z | 2012-03-04T00:00:00.005500Z - 2012-03-04T23:59:59.805500Z | 5.0 Hz, 432000 samples
    >>> daynoise.window
    7200.0
    >>> daynoise.overlap
    0.3
    >>> daynoise.key
    '7D.M08A'
    >>> daynoise.ncomp
    4
    >>> daynoise.tf_list
    {'ZP': True, 'Z1': True, 'Z2-1': True, 'ZP-21': True, 'ZH': True, 'ZP-H': True}

    """
    def __init__(self, tr1=None, tr2=None, trZ=None, trP=None, window=None, \
        overlap=None, key=None):

        # Load example data if initializing empty object
        if all(value == None for value in [tr1, tr2, trZ, trP]):
            print("Uploading demo data")
            import os
            st = read(os.path.join(os.path.dirname(__file__), "../examples/data/2012March04", \
                "*.SAC"))
            tr1 = st.select(component='1')[0]
            tr2 = st.select(component='2')[0]
            trZ = st.select(component='Z')[0]
            trP = st.select(component='P')[0]
            window = 7200.
            overlap = 0.3
            key = '7D.M08A'

        # Check that all traces are valid Trace objects
        for tr in [tr1, tr2, trZ, trP]:
            if not isinstance(tr, Trace):
                raise(Exception("Error initializing DayNoise object - "\
                    +str(tr)+" is not a Trace object"))

        # Unpack everything
        self.tr1 = tr1
        self.tr2 = tr2
        self.trZ = trZ
        self.trP = trP
        self.window = window
        self.overlap = overlap
        self.key = key

        # Get trace attributes
        self.dt = self.trZ.stats.delta
        self.npts = self.trZ.stats.npts
        self.fs = self.trZ.stats.sampling_rate
        self.year = self.trZ.stats.starttime.year
        self.julday = self.trZ.stats.starttime.julday

        # Get number of components for the available, non-empty traces
        self.ncomp = np.sum(1 for tr in 
            Stream(traces=[tr1,tr2,trZ,trP]) if np.any(tr.data))

        # Build list of available transfer functions based on the number of components
        if self.ncomp==2:
            self.tf_list = {'ZP': True, 'Z1':False, 'Z2-1':False, 'ZP-21':False, 'ZH':False, 'ZP-H':False}
        elif self.ncomp==3:
            self.tf_list = {'ZP': False, 'Z1':True, 'Z2-1':True, 'ZP-21':False, 'ZH':True, 'ZP-H':False}
        else:
            self.tf_list = {'ZP': True, 'Z1':True, 'Z2-1':True, 'ZP-21':True, 'ZH':True, 'ZP-H':True}


    def QC_daily_spectra(self, pd=[0.004, 0.2], tol=1.5, alpha=0.05, smooth=True, fig_QC=False, debug=False):
        """
        Method to determine daily time windows for which the spectra are 
        anomalous and should be discarded in the calculation of the
        transfer functions. 

        Parameters
        ----------
        pd : list
            Frequency corners of passband for calculating the spectra
        tol : float
            Tolerance threshold. If spectrum > std*tol, window is flagged as bad
        alpha : float
            Confidence interval for f-test
        smooth : boolean
            Determines if the smoothed (True) or raw (False) spectra are used
        fig_QC : boolean
            Whether or not to produce a figure showing the results of the quality control
        debug : boolean
            Whether or not to plot intermediate steps in the QC procedure for debugging

        Attributes
        ----------
        goodwins : list 
            List of booleans representing whether a window is good (True) or not (False)

        Example
        -------

        Perform QC on DayNoise object using default values and plot final figure

        >>> from obstools.atacr.classes import DayNoise
        >>> daynoise = DayNoise()
        >>> daynoise.QC_daily_spectra(fig_QC=True)

        .. figure:: ../obstools/examples/figures/Figure_3a.png
           :align: center

        >>> daynoise.goodwins
        array([False,  True,  True,  True,  True,  True,  True,  True, False,
           False,  True,  True,  True,  True,  True,  True], dtype=bool)

        """

        # Points in window
        ws = int(self.window/self.dt)

        # Number of points to overlap
        ss = int(self.window*self.overlap/self.dt)

        # hanning window
        hanning = np.hanning(2*ss)
        wind = np.ones(ws)
        wind[0:ss] = hanning[0:ss]
        wind[-ss:ws] = hanning[ss:ws]

        # Get spectrograms for single day-long keys
        psd1 = None; psd2 = None; psdZ = None; psdP = None
        f, t, psdZ = spectrogram(self.trZ.data, self.fs, window=wind, nperseg=ws, noverlap=ss)
        if self.ncomp==2 or self.ncomp==4:
            f, t, psdP = spectrogram(self.trP.data, self.fs, window=wind, nperseg=ws, noverlap=ss)
        if self.ncomp==3 or self.ncomp==4:
            f, t, psd1 = spectrogram(self.tr1.data, self.fs, window=wind, nperseg=ws, noverlap=ss)
            f, t, psd2 = spectrogram(self.tr2.data, self.fs, window=wind, nperseg=ws, noverlap=ss)

        if debug:
            if self.ncomp==2:
                plt.figure(1)
                plt.subplot(2,1,1)
                plt.pcolormesh(t, f, np.log(psdZ))
                plt.title('Z', fontdict={'fontsize': 8})
                plt.subplot(2,1,2)
                plt.pcolormesh(t, f, np.log(psdP))
                plt.title('P', fontdict={'fontsize': 8})
                plt.xlabel('Seconds')
                plt.tight_layout()
                plt.show()

            elif self.ncomp==3:
                plt.figure(1)
                plt.subplot(3,1,1)
                plt.pcolormesh(t, f, np.log(psd1))
                plt.title('H1', fontdict={'fontsize': 8})
                plt.subplot(3,1,2)
                plt.pcolormesh(t, f, np.log(psd2))
                plt.title('H2', fontdict={'fontsize': 8})
                plt.subplot(3,1,3)
                plt.pcolormesh(t, f, np.log(psdZ))
                plt.title('Z', fontdict={'fontsize': 8})
                plt.xlabel('Seconds')
                plt.tight_layout()
                plt.show()

            else:
                plt.figure(1)
                plt.subplot(4,1,1)
                plt.pcolormesh(t, f, np.log(psd1))
                plt.title('H1', fontdict={'fontsize': 8})
                plt.subplot(4,1,2)
                plt.pcolormesh(t, f, np.log(psd2))
                plt.title('H2', fontdict={'fontsize': 8})
                plt.subplot(4,1,3)
                plt.pcolormesh(t, f, np.log(psdZ))
                plt.title('Z', fontdict={'fontsize': 8})
                plt.subplot(4,1,4)
                plt.pcolormesh(t, f, np.log(psdP))
                plt.title('P', fontdict={'fontsize': 8})
                plt.xlabel('Seconds')
                plt.tight_layout()
                plt.show()

        # Select bandpass frequencies
        ff = (f>pd[0]) & (f<pd[1])

        if smooth:
            # Smooth out the log of the PSDs
            sl_psd1 = None; sl_psd2 = None; sl_psdZ = None; sl_psdP = None
            sl_psdZ = utils.smooth(np.log(psdZ), 50, axis=0)
            if self.ncomp==2 or self.ncomp==4:
                sl_psdP = utils.smooth(np.log(psdP), 50, axis=0)
            if self.ncomp==3 or self.ncomp==4:
                sl_psd1 = utils.smooth(np.log(psd1), 50, axis=0)
                sl_psd2 = utils.smooth(np.log(psd2), 50, axis=0)

        else:
            # Take the log of the PSDs
            sl_psd1 = None; sl_psd2 = None; sl_psdZ = None; sl_psdP = None
            sl_psdZ = np.log(psdZ)
            if self.ncomp==2 or self.ncomp==4:
                sl_psdP = np.log(psdP)
            if self.ncomp==3 or self.ncomp==4:
                sl_psd1 = np.log(psd1)
                sl_psd2 = np.log(psd2)

        # Remove mean of the log PSDs
        dsl_psdZ = sl_psdZ[ff,:] - np.mean(sl_psdZ[ff,:], axis=0)
        if self.ncomp==2:
            dsl_psdP = sl_psdP[ff,:] - np.mean(sl_psdP[ff,:], axis=0)
            dsls = [dsl_psdZ, dsl_psdP]
        elif self.ncomp==3:
            dsl_psd1 = sl_psd1[ff,:] - np.mean(sl_psd1[ff,:], axis=0)
            dsl_psd2 = sl_psd2[ff,:] - np.mean(sl_psd2[ff,:], axis=0)
            dsls = [dsl_psd1, dsl_psd2, dsl_psdZ]
        else:
            dsl_psd1 = sl_psd1[ff,:] - np.mean(sl_psd1[ff,:], axis=0)
            dsl_psd2 = sl_psd2[ff,:] - np.mean(sl_psd2[ff,:], axis=0)
            dsl_psdP = sl_psdP[ff,:] - np.mean(sl_psdP[ff,:], axis=0)
            dsls = [dsl_psd1, dsl_psd2, dsl_psdZ, dsl_psdP]

        if debug:
            if self.ncomp==2:
                plt.figure(2)
                plt.subplot(2,1,1)
                plt.semilogx(f, sl_psdZ, 'g', lw=0.5)
                plt.subplot(2,1,2)
                plt.semilogx(f, sl_psdP, 'k', lw=0.5)
                plt.tight_layout()
                plt.show()
            elif self.ncomp==3:
                plt.figure(2)
                plt.subplot(3,1,1)
                plt.semilogx(f, sl_psd1, 'r', lw=0.5)
                plt.subplot(3,1,2)
                plt.semilogx(f, sl_psd2, 'b', lw=0.5)
                plt.subplot(3,1,3)
                plt.semilogx(f, sl_psdZ, 'g', lw=0.5)
                plt.tight_layout()
                plt.show()
            else:
                plt.figure(2)
                plt.subplot(4,1,1)
                plt.semilogx(f, sl_psd1, 'r', lw=0.5)
                plt.subplot(4,1,2)
                plt.semilogx(f, sl_psd2, 'b', lw=0.5)
                plt.subplot(4,1,3)
                plt.semilogx(f, sl_psdZ, 'g', lw=0.5)
                plt.subplot(4,1,4)
                plt.semilogx(f, sl_psdP, 'k', lw=0.5)
                plt.tight_layout()
                plt.show()

        # Cycle through to kill high-std-norm windows
        moveon = False
        goodwins = np.repeat([True], len(t))
        indwin = np.argwhere(goodwins==True)

        while moveon == False:

            ubernorm = np.empty((self.ncomp, np.sum(goodwins)))
            for ind_u, dsl in enumerate(dsls):
                normvar = np.zeros(np.sum(goodwins))
                for ii,tmp in enumerate(indwin):
                    ind = np.copy(indwin); ind = np.delete(ind, ii)
                    normvar[ii] = norm(np.std(dsl[:, ind], axis=1), ord=2)
                ubernorm[ind_u, :] = np.median(normvar) - normvar 

            penalty = np.sum(ubernorm, axis=0)

            if debug:
                plt.figure(4)
                for i in range(self.ncomp):
                    plt.plot(range(0,np.sum(goodwins)), detrend(ubernorm, type='constant')[i], 'o-')
                plt.show()
                plt.figure(5)
                plt.plot(range(0,np.sum(goodwins)), np.sum(ubernorm, axis=0), 'o-')
                plt.show()

            kill = penalty > tol*np.std(penalty)
            if np.sum(kill)==0: 
                self.goodwins = goodwins
                moveon = True
                if fig_QC:
                    power = Power(sl_psd1, sl_psd2, sl_psdZ, sl_psdP)
                    plot.fig_QC(f, power, goodwins, self.ncomp, key=self.key)
                return
 
            trypenalty = penalty[np.argwhere(kill == False)].T[0]

            if utils.ftest(penalty, 1, trypenalty, 1) < alpha:
                goodwins[indwin[kill==True]] = False
                indwin = np.argwhere(goodwins==True)
                moveon = False
            else:
                moveon = True

        self.goodwins = goodwins

        if fig_QC:
            power = Power(sl_psd1, sl_psd2, sl_psdZ, sl_psdP)
            plot.fig_QC(f, power, goodwins, self.ncomp, key=self.key)


    def average_daily_spectra(self, calc_rotation=True, fig_average=False, fig_coh_ph=False, debug=False):
        """
        Method to average the daily spectra for good windows. By default, the method
        will attempt to calculate the azimuth of maximum coherence between horizontal
        components and the vertical component (for maximum tilt direction), and use 
        the rotated horizontals in the transfer function calculations.

        Parameters
        ----------
        calc_rotation : boolean
            Whether or not to calculate the tilt direction
        fig_average : boolean
            Whether or not to produce a figure showing the average daily spectra
        fig_coh_ph : boolean
            Whether or not to produce a figure showing the maximum coherence between H and Z
        debug : boolean
            Whether or not to plot intermediate steps in the QC procedure for debugging

        Attributes
        ----------
        f : :class:`~numpy.ndarray` 
            Positive frequency axis for corresponding window parameters
        power : :class:`~obstools.atacr.classes.Power`
            Container for the Power spectra
        cross : :class:`~obstools.atacr.classes.Cross`
            Container for the Cross power spectra
        rotation : :class:`~obstools.atacr.classes.Cross`, optional
            Container for the Rotated power and cross spectra

        Example
        -------

        Average spectra for good windows using default values and plot final figure

        >>> from obstools.atacr.classes import DayNoise
        >>> daynoise = DayNoise()
        >>> daynoise.QC_daily_spectra()
        >>> daynoise.average_daily_spectra(fig_average=True)

        .. figure:: ../obstools/examples/figures/Figure_3b.png
           :align: center

        >>> daynoise.power
        <obstools.atacr.classes.Power object at 0x12e353860>

        """

        # Points in window
        ws = int(self.window/self.dt)

        # Number of points in step
        ss = int(self.window*(1.-self.overlap)/self.dt)

        ft1 = None; ft2 = None; ftZ = None; ftP = None
        ftZ, f = utils.calculate_windowed_fft(self.trZ, ws, ss)
        if self.ncomp==2 or self.ncomp==4:
            ftP, f = utils.calculate_windowed_fft(self.trP, ws, ss)
        if self.ncomp==3 or self.ncomp==4:
            ft1, f = utils.calculate_windowed_fft(self.tr1, ws, ss)
            ft2, f = utils.calculate_windowed_fft(self.tr2, ws, ss)

        self.f = f

        # Extract good windows
        c11 = None; c22 = None; cZZ = None; cPP = None
        cZZ = np.abs(np.mean(ftZ[self.goodwins,:]*np.conj(ftZ[self.goodwins,:]), axis=0))[0:len(f)]
        if self.ncomp==2 or self.ncomp==4:
            cPP = np.abs(np.mean(ftP[self.goodwins,:]*np.conj(ftP[self.goodwins,:]), axis=0))[0:len(f)]
        if self.ncomp==3 or self.ncomp==4:
            c11 = np.abs(np.mean(ft1[self.goodwins,:]*np.conj(ft1[self.goodwins,:]), axis=0))[0:len(f)]
            c22 = np.abs(np.mean(ft2[self.goodwins,:]*np.conj(ft2[self.goodwins,:]), axis=0))[0:len(f)]

        # Extract bad windows
        bc11 = None; bc22 = None; bcZZ = None; bcPP = None
        if np.sum(~self.goodwins) > 0:
            bcZZ = np.abs(np.mean(ftZ[~self.goodwins,:]*np.conj(ftZ[~self.goodwins,:]), axis=0))[0:len(f)]
            if self.ncomp==2 or self.ncomp==4:
                bcPP = np.abs(np.mean(ftP[~self.goodwins,:]*np.conj(ftP[~self.goodwins,:]), axis=0))[0:len(f)]
            if self.ncomp==3 or self.ncomp==4:
                bc11 = np.abs(np.mean(ft1[~self.goodwins,:]*np.conj(ft1[~self.goodwins,:]), axis=0))[0:len(f)]
                bc22 = np.abs(np.mean(ft2[~self.goodwins,:]*np.conj(ft2[~self.goodwins,:]), axis=0))[0:len(f)]

        # Calculate mean of all good windows if component combinations exist
        c12 = None; c1Z = None; c2Z = None; c1P = None; c2P = None; cZP = None
        if self.ncomp==3 or self.ncomp==4:
            c12 = np.mean(ft1[self.goodwins,:]*np.conj(ft2[self.goodwins,:]), axis=0)[0:len(f)]
            c1Z = np.mean(ft1[self.goodwins,:]*np.conj(ftZ[self.goodwins,:]), axis=0)[0:len(f)]
            c2Z = np.mean(ft2[self.goodwins,:]*np.conj(ftZ[self.goodwins,:]), axis=0)[0:len(f)]
        if self.ncomp==4:
            c1P = np.mean(ft1[self.goodwins,:]*np.conj(ftP[self.goodwins,:]), axis=0)[0:len(f)]
            c2P = np.mean(ft2[self.goodwins,:]*np.conj(ftP[self.goodwins,:]), axis=0)[0:len(f)]
        if self.ncomp==2 or self.ncomp==4:
            cZP = np.mean(ftZ[self.goodwins,:]*np.conj(ftP[self.goodwins,:]), axis=0)[0:len(f)]

        # Store as attributes
        self.power = Power(c11, c22, cZZ, cPP)
        self.cross = Cross(c12, c1Z, c1P, c2Z, c2P, cZP)
        bad = Power(bc11, bc22, bcZZ, bcPP)

        if fig_average:
            plot.fig_average(f, self.power, bad, self.goodwins, self.ncomp, key=self.key)

        if calc_rotation and self.ncomp>=3:
            cHH, cHZ, cHP, coh, ph, direc, tilt, coh_value, phase_value = utils.calculate_tilt( \
                ft1, ft2, ftZ, ftP, f, self.goodwins)
            self.rotation = Rotation(cHH, cHZ, cHP, coh, ph, tilt, coh_value, phase_value, direc)

            if fig_coh_ph:
                plot.fig_coh_ph(coh, ph, direc)
        else:
            self.rotation = Rotation()


    def save(self, filename):
        """
        Method to save the object to file using `~Pickle`.

        Parameters
        ----------
        filename : str
            File name 

        Example
        -------

        >>> from obstools.atacr.classes import DayNoise
        >>> daynoise = DayNoise()
        >>> daynoise.QC_daily_spectra()
        >>> daynoise.average_daily_spectra()
        >>> daynoise.save('daynoise_demo.pkl')
        >>> import glob
        >>> glob.glob("./daynoise_demo.pkl")
        ['./daynoise_demo.pkl']

        """

        # Remove original traces to save disk space
        del self.tr1 
        del self.tr2 
        del self.trZ
        del self.trP

        file = open(filename, 'wb')
        pickle.dump(self, file)
        file.close()


class StaNoise(object):
    """
    A StaNoise object contains attributes that associate
    three-component raw (or deconvolved) traces, metadata information
    and window parameters.

    Note
    ----
    The object is initialized with :class:`~obstools.atacr.classes.Power`,
    :class:`~obstools.atacr.classes.Cross` and :class:`~obstools.atacr.classes.Rotation` 
    objects. Each individual spectral quantity is unpacked as an object attribute, 
    but all of them are discarded as the object is saved to disk and new container objects
    are defined and saved.

    Attributes
    ----------
    f : :class:`~numpy.ndarray`
        Frequency axis for corresponding time sampling parameters
    nwins : int
        Number of good windows from the :class:`~obstools.atacr.classes.DayNoise` object
    key : str
        Station key for current object
    ncomp : int
        Number of available components (either 2, 3 or 4)
    tf_list : Dict
        Dictionary of possible transfer functions given the available components. 
    power : :class:`~obstools.atacr.classes.Power`
        Container for station-averaged spectral power for all available components
    cross :
        Container for station-averaged cross spectral power for all available components
    rotation :
        Container for station-averaged rotated (cross) spectral power for all available components
    gooddays : list 
        List of booleans representing whether a day is good (True) or not (False). 
        This attribute is returned from the method :func:`~obstools.atacr.classes.StaNoise.QC_sta_spectra`

    """
    def __init__(self, power, cross, rotation, f, nwins, ncomp, key):

        if all(value == None for value in power.values()):
            raise(Exception("Container Power is empty - aborting"))
        if all(value == None for value in cross.values()):
            raise(Exception("Container Cross is empty - aborting"))

        # Unbox the container attributes
        self.c11 = power.c11.T
        self.c22 = power.c22.T
        self.cZZ = power.cZZ.T
        self.cPP = power.cPP.T
        self.c12 = cross.c12.T
        self.c1Z = cross.c1Z.T
        self.c1P = cross.c1P.T
        self.c2Z = cross.c2Z.T
        self.c2P = cross.c2P.T
        self.cZP = cross.cZP.T
        self.cHH = rotation.cHH.T
        self.cHZ = rotation.cHZ.T
        self.cHP = rotation.cHP.T
        self.tilt = rotation.tilt

        self.f = f
        self.nwins = nwins
        self.key = key
        self.ncomp = ncomp

        # Build list of available transfer functions for future use
        if self.ncomp==2:
            self.tf_list = {'ZP': True, 'Z1':False, 'Z2-1':False, 'ZP-21':False, 'ZH':False, 'ZP-H':False}
        elif self.ncomp==3:
            self.tf_list = {'ZP': False, 'Z1':True, 'Z2-1':True, 'ZP-21':False, 'ZH':False, 'ZP-H':False}
        else:
            self.tf_list = {'ZP': True, 'Z1':True, 'Z2-1':True, 'ZP-21':True, 'ZH':False, 'ZP-H':False}


    def QC_sta_spectra(self, pd=[0.004, 0.2], tol=2.0, alpha=0.05, fig_QC=False, debug=False):
        """
        Method to determine the days (for given time window) for which the spectra are 
        anomalous and should be discarded in the calculation of the
        long-term transfer functions. 

        Parameters
        ----------
        pd : list
            Frequency corners of passband for calculating the spectra
        tol : float
            Tolerance threshold. If spectrum > std*tol, window is flagged as bad
        alpha : float
            Confidence interval for f-test
        fig_QC : boolean
            Whether or not to produce a figure showing the results of the quality control
        debug : boolean
            Whether or not to plot intermediate steps in the QC procedure for debugging

        Attributes
        ----------
        goodwins : list 
            List of booleans representing whether a window is good (True) or not (False)

        """

        # Select bandpass frequencies
        ff = (self.f>pd[0]) & (self.f<pd[1])

        # Smooth out the log of the PSDs
        sl_cZZ = None; sl_c11 = None; sl_c22 = None; sl_cPP = None
        sl_cZZ = utils.smooth(np.log(self.cZZ), 50, axis=0)
        if self.ncomp==2 or self.ncomp==4:
            sl_cPP = utils.smooth(np.log(self.cPP), 50, axis=0)
        if self.ncomp==3 or self.ncomp==4:
            sl_c11 = utils.smooth(np.log(self.c11), 50, axis=0)
            sl_c22 = utils.smooth(np.log(self.c22), 50, axis=0)

        # Remove mean of the log PSDs
        dsl_cZZ = sl_cZZ[ff,:] - np.mean(sl_cZZ[ff,:], axis=0)
        if self.ncomp==2:
            dsl_cPP = sl_cPP[ff,:] - np.mean(sl_cPP[ff,:], axis=0)
            dsls = [dsl_cZZ, dsl_cPP]
        elif self.ncomp==3:
            dsl_c11 = sl_c11[ff,:] - np.mean(sl_c11[ff,:], axis=0)
            dsl_c22 = sl_c22[ff,:] - np.mean(sl_c22[ff,:], axis=0)
            dsls = [dsl_c11, dsl_c22, dsl_cZZ]
        else:
            dsl_c11 = sl_c11[ff,:] - np.mean(sl_c11[ff,:], axis=0)
            dsl_c22 = sl_c22[ff,:] - np.mean(sl_c22[ff,:], axis=0)
            dsl_cPP = sl_cPP[ff,:] - np.mean(sl_cPP[ff,:], axis=0)
            dsls = [dsl_c11, dsl_c22, dsl_cZZ, dsl_cPP]

        if debug:
            if self.ncomp==2:
                plt.figure(2)
                plt.subplot(2,1,1)
                plt.semilogx(self.f, sl_cZZ, 'g', lw=0.5)
                plt.subplot(2,1,2)
                plt.semilogx(self.f, sl_cPP, 'k', lw=0.5)
                plt.tight_layout()
                plt.show()
            elif self.ncomp==3:
                plt.figure(2)
                plt.subplot(3,1,1)
                plt.semilogx(self.f, sl_c11, 'r', lw=0.5)
                plt.subplot(3,1,2)
                plt.semilogx(self.f, sl_c22, 'b', lw=0.5)
                plt.subplot(3,1,3)
                plt.semilogx(self.f, sl_cZZ, 'g', lw=0.5)
                plt.tight_layout()
                plt.show()
            else:
                plt.figure(2)
                plt.subplot(4,1,1)
                plt.semilogx(self.f, sl_c11, 'r', lw=0.5)
                plt.subplot(4,1,2)
                plt.semilogx(self.f, sl_c22, 'b', lw=0.5)
                plt.subplot(4,1,3)
                plt.semilogx(self.f, sl_cZZ, 'g', lw=0.5)
                plt.subplot(4,1,4)
                plt.semilogx(self.f, sl_cPP, 'k', lw=0.5)
                plt.tight_layout()
                plt.show()

        # Cycle through to kill high-std-norm windows
        moveon = False
        gooddays = np.repeat([True], self.cZZ.shape[1])
        indwin = np.argwhere(gooddays==True)

        while moveon == False:
            ubernorm = np.empty((self.ncomp, np.sum(gooddays)))
            for ind_u, dsl in enumerate(dsls):
                normvar = np.zeros(np.sum(gooddays))
                for ii,tmp in enumerate(indwin):
                    ind = np.copy(indwin); ind = np.delete(ind, ii)
                    normvar[ii] = norm(np.std(dsl[:, ind], axis=1), ord=2)
                ubernorm[ind_u, :] = np.median(normvar) - normvar 

            penalty = np.sum(ubernorm, axis=0)

            if debug:
                plt.figure(4)
                for i in range(self.ncomp):
                    plt.plot(range(0,np.sum(gooddays)), detrend(ubernorm, type='constant')[i], 'o-')
                plt.show()
                plt.figure(5)
                plt.plot(range(0,np.sum(gooddays)), np.sum(ubernorm, axis=0), 'o-')
                plt.show()

            kill = penalty > tol*np.std(penalty)
            if np.sum(kill)==0: 
                self.gooddays = gooddays
                moveon = True
                if fig_QC:
                    power = Power(sl_c11, sl_c22, sl_cZZ, sl_cPP)
                    plot.fig_QC(self.f, power, gooddays, self.ncomp, key=self.key)
                return

            trypenalty = penalty[np.argwhere(kill == False)].T[0]

            if utils.ftest(penalty, 1, trypenalty, 1) < alpha:
                gooddays[indwin[kill==True]] = False
                indwin = np.argwhere(gooddays==True)
                moveon = False
            else:
                moveon = True

        self.gooddays = gooddays

        if fig_QC:
            power = Power(sl_c11, sl_c22, sl_cZZ, sl_cPP)
            plot.fig_QC(self.f, power, gooddays, self.ncomp, key=self.key)

    def average_sta_spectra(self, fig_average=False, debug=False):
        """
        Method to average the daily station spectra for good windows.

        Parameters
        ----------
        fig_average : boolean
            Whether or not to produce a figure showing the average daily spectra
        debug : boolean
            Whether or not to plot intermediate steps in the QC procedure for debugging

        Attributes
        ----------
        power : :class:`~obstools.atacr.classes.Power`
            Container for the Power spectra
        cross : :class:`~obstools.atacr.classes.Cross`
            Container for the Cross power spectra
        rotation : :class:`~obstools.atacr.classes.Cross`, optional
            Container for the Rotated power and cross spectra

        """

        # Power spectra
        c11 = None; c22 = None; cZZ = None; cPP = None
        cZZ = np.sum(self.cZZ[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
        if self.ncomp==2 or self.ncomp==4:
            cPP = np.sum(self.cPP[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
        if self.ncomp==3 or self.ncomp==4:
            c11 = np.sum(self.c11[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
            c22 = np.sum(self.c22[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])

        # Bad days - for plotting
        bc11 = None; bc22 = None; bcZZ = None; bcPP = None
        if np.sum(~self.gooddays) > 0:
            bcZZ = np.sum(self.cZZ[:, ~self.gooddays]*self.nwins[~self.gooddays], axis=1)/np.sum(self.nwins[~self.gooddays])
            if self.ncomp==2 or self.ncomp==4:            
                bcPP = np.sum(self.cPP[:, ~self.gooddays]*self.nwins[~self.gooddays], axis=1)/np.sum(self.nwins[~self.gooddays])
            if self.ncomp==3 or self.ncomp==4:
                bc11 = np.sum(self.c11[:, ~self.gooddays]*self.nwins[~self.gooddays], axis=1)/np.sum(self.nwins[~self.gooddays])
                bc22 = np.sum(self.c22[:, ~self.gooddays]*self.nwins[~self.gooddays], axis=1)/np.sum(self.nwins[~self.gooddays])

        # Cross spectra
        c12 = None; c1Z = None; c2Z = None; c1P = None; c2P = None; cZP = None
        if self.ncomp==3 or self.ncomp==4:
            c12 = np.sum(self.c12[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
            c1Z = np.sum(self.c1Z[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
            c2Z = np.sum(self.c2Z[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
        if self.ncomp==4:
            c1P = np.sum(self.c1P[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
            c2P = np.sum(self.c2P[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
        if self.ncomp==2 or self.ncomp==4:
            cZP = np.sum(self.cZP[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])

        # Rotated component
        cHH = None; cHZ = None; cHP = None
        if self.ncomp==3 or self.ncomp==4:
            cHH = np.sum(self.cHH[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
            cHZ = np.sum(self.cHZ[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])
        if self.ncomp==4:
            cHP = np.sum(self.cHP[:, self.gooddays]*self.nwins[self.gooddays], axis=1)/np.sum(self.nwins[self.gooddays])

        self.power = Power(c11, c22, cZZ, cPP)
        self.cross = Cross(c12, c1Z, c1P, c2Z, c2P, cZP)
        self.rotation = Rotation(cHH, cHZ, cHP)
        bad = Power(bc11, bc22, bcZZ, bcPP)

        if fig_average:
            plot.fig_average(self.f, self.power, bad, self.gooddays, self.ncomp, key=self.key)


    def save(self, filename):
        """
        Method to save the object to file using `~Pickle`.

        Parameters
        ----------
        filename : str
            File name 

        """

        # Remove traces to save disk space
        del self.c11 
        del self.c22 
        del self.cZZ
        del self.cPP
        del self.c12 
        del self.c1Z 
        del self.c1P
        del self.c2Z
        del self.c2P
        del self.cZP

        file = open(filename, 'wb')
        pickle.dump(self, file)
        file.close()


class TFNoise(object):
    """
    A TFNoise object contains attributes that store the transfer function information
    from multiple components (and component combinations). 

    Note
    ----
    The object is initialized with :class:`~obstools.atacr.classes.Power`,
    :class:`~obstools.atacr.classes.Cross` and :class:`~obstools.atacr.classes.Rotation` 
    objects. Each individual spectral quantity is unpacked as an object attribute, 
    but all of them are discarded as the object is saved to disk and new container objects
    are defined and saved.

    Attributes
    ----------
    f : :class:`~numpy.ndarray`
        Frequency axis for corresponding time sampling parameters
    tf_list : Dict
        Dictionary of possible transfer functions given the available components. 
    transfunc : Dict
        Dictionary of transfer function arrays for the list of available functions.

    """

    def __init__(self, f, power, cross, rotation, tf_list):

        if all(value == None for value in power.values()):
            raise(Exception("Container Power is empty - aborting"))
        if all(value == None for value in cross.values()):
            raise(Exception("Container Cross is empty - aborting"))

        self.f = f
        self.c11 = power.c11
        self.c22 = power.c22
        self.cZZ = power.cZZ
        self.cPP = power.cPP
        self.cHH = rotation.cHH
        self.cHZ = rotation.cHZ
        self.cHP = rotation.cHP
        self.c12 = cross.c12
        self.c1Z = cross.c1Z
        self.c1P = cross.c1P
        self.c2Z = cross.c2Z
        self.c2P = cross.c2P
        self.cZP = cross.cZP
        self.tilt = rotation.tilt
        self.tf_list = tf_list

    class TfDict(dict):

        def __init__(self):
            self = dict()

        def add(self, key, value):
            self[key] = value

    def transfer_func(self):
        """
        Method to calculate transfer functions between multiple components (and 
        component combinations) from the averaged (daily or station-averaged) noise spectra.

        Attributes
        ----------
        transfunc : :class:`~obstools.atacr.classes.TFNoise.TfDict`
            Container Dictionary for all possible transfer functions

        """

        transfunc = self.TfDict()

        for key, value in self.tf_list.items():

            if key == 'ZP':
                if value:
                    tf_ZP = {'TF_ZP': self.cZP/self.cPP}
                    transfunc.add('ZP', tf_ZP)

            elif key == 'Z1':
                if value:
                    tf_Z1 = {'TF_Z1': np.conj(self.c1Z)/self.c11}
                    transfunc.add('Z1', tf_Z1)

            elif key == 'Z2-1':
                if value:
                    lc1c2 = np.conj(self.c12)/self.c11
                    coh_12 = utils.coherence(self.c12, self.c11, self.c22)
                    gc2c2_c1 = self.c22*(1. - coh_12)
                    gc2cZ_c1 = np.conj(self.c2Z) - np.conj(lc1c2*self.c1Z)
                    lc2cZ_c1 = gc2cZ_c1/gc2c2_c1
                    tf_Z2_1 = {'TF_21': lc1c2, 'TF_Z2-1': lc2cZ_c1}
                    transfunc.add('Z2-1', tf_Z2_1)

            elif key == 'ZP-21':
                if value:
                    lc1cZ = np.conj(self.c1Z)/self.c11
                    lc1c2 = np.conj(self.c12)/self.c11
                    lc1cP = np.conj(self.c1P)/self.c11
                    
                    coh_12 = utils.coherence(self.c12, self.c11, self.c22)
                    coh_1P = utils.coherence(self.c1P, self.c11, self.cPP)
                    
                    gc2c2_c1 = self.c22*(1. - coh_12)
                    gcPcP_c1 = self.cPP*(1. - coh_1P)
                    
                    gc2cZ_c1 = np.conj(self.c2Z) - np.conj(lc1c2*self.c1Z)
                    gcPcZ_c1 = self.cZP - np.conj(lc1cP*self.c1Z)

                    gc2cP_c1 = np.conj(self.c2P) - np.conj(lc1c2*self.c1P)

                    lc2cP_c1 = gc2cP_c1/gc2c2_c1
                    lc2cZ_c1 = gc2cZ_c1/gc2c2_c1

                    coh_c2cP_c1 = utils.coherence(gc2cP_c1, gc2c2_c1, gcPcP_c1)

                    gcPcP_c1c2 = gcPcP_c1*(1. - coh_c2cP_c1)
                    gcPcZ_c1c2 = gcPcZ_c1 - np.conj(lc2cP_c1)*gc2cZ_c1

                    lcPcZ_c2c1 = gcPcZ_c1c2/gcPcP_c1c2

                    tf_ZP_21 = {'TF_Z1':lc1cZ, 'TF_21':lc1c2, 'TF_P1':lc1cP, \
                        'TF_P2-1':lc2cP_c1, 'TF_Z2-1':lc2cZ_c1, 'TF_ZP-21':lcPcZ_c2c1}
                    transfunc.add('ZP-21', tf_ZP_21)

            elif key == 'ZH':
                if value:
                    tf_ZH = {'TF_ZH': np.conj(self.cHZ)/self.cHH}
                    transfunc.add('ZH', tf_ZH)

            elif key == 'ZP-H':
                if value:
                    lcHcP = np.conj(self.cHP)/self.cHH
                    coh_HP = utils.coherence(self.cHP, self.cHH, self.cPP)
                    gcPcP_cH = self.cPP*(1. - coh_HP)
                    gcPcZ_cH = self.cZP - np.conj(lcHcP*self.cHZ)
                    lcPcZ_cH = gcPcZ_cH/gcPcP_cH
                    tf_ZP_H = {'TF_PH': lcHcP, 'TF_ZP-H': lcPcZ_cH}
                    transfunc.add('ZP-H', tf_ZP_H)

            else:
                raise(Exception('Incorrect key'))

            self.transfunc = transfunc

    def save(self, filename):
        """
        Method to save the object to file using `~Pickle`.

        Parameters
        ----------
        filename : str
            File name 

        """

        # Remove traces to save disk space
        del self.c11 
        del self.c22 
        del self.cZZ
        del self.cPP
        del self.cHH
        del self.cHZ
        del self.cHP
        del self.c12 
        del self.c1Z 
        del self.c1P
        del self.c2Z
        del self.c2P
        del self.cZP
        file = open(filename, 'wb')
        pickle.dump(self, file)
        file.close()


class EventStream(object):
    """
    An EventStream object contains attributes that store station-event metadata and 
    methods for applying the transfer functions to the various components and produce
    corrected/cleaned vertical components.

    Note
    ----
    An ``EventStream`` object is defined as the data (:class:`~obspy.core.Stream` object) 
    are read from file or downloaded from an ``obspy`` Client. Based on the available 
    components, a list of possible corrections is determined automatically.

    Attributes
    ----------
    sta : :class:`~stdb.StdbElement`
        An instance of an stdb object
    key : str
        Station key for current object
    sth : :class:`~obspy.core.Stream`
        Stream containing three-component seismic data (traces are empty if data are not available)
    stp : :class:`~obspy.core.Stream`
        Stream containing pressure data (trace is empty if data are not available)
    tstamp : str
        Time stamp for event
    evlat : float
        Latitude of seismic event
    evlon : float
        Longitude of seismic event
    evtime : :class:`~obspy.core.UTCDateTime`
        Origin time of seismic event
    window : float
        Length of time window in seconds
    fs : float
        Sampling frequency (in Hz)
    dt : float
        Sampling distance in seconds
    npts : int
        Number of points in time series
    ncomp : int
        Number of available components (either 2, 3 or 4)
    ev_list : Dict
        Dictionary of possible transfer functions given the available components. This is determined
        during initialization.
    correct : :class:`~obstools.atacr.classes.EventStream.CorrectDict`
        Container Dictionary for all possible corrections from the transfer functions. This is 
        calculated from the method :func:`~obstools.atacr.classes.EventStream.correct_data`

    """

    def __init__(self, sta, sth, stp, tstamp, lat, lon, time, window, sampling_rate, ncomp):
        self.sta = sta
        self.key = sta.network+'.'+sta.station
        self.sth = sth
        self.stp = stp
        self.tstamp = tstamp
        self.evlat = lat
        self.evlon = lon
        self.evtime = time
        self.window = window
        self.fs = sampling_rate
        self.dt = 1./sampling_rate
        self.ncomp = ncomp

        # Build list of available transfer functions for future use
        if self.ncomp==2:
            self.ev_list = {'ZP': True, 'Z1':False, 'Z2-1':False, 'ZP-21':False, 'ZH':False, 'ZP-H':False}
        elif self.ncomp==3:
            self.ev_list = {'ZP': False, 'Z1':True, 'Z2-1':True, 'ZP-21':False, 'ZH':True, 'ZP-H':False}
        else:
            self.ev_list = {'ZP': True, 'Z1':True, 'Z2-1':True, 'ZP-21':True, 'ZH':True, 'ZP-H':True}

    class CorrectDict(dict):

        def __init__(self):
            self = dict()

        def add(self, key, value):
            self[key] = value

    def correct_data(self, tfnoise):
        """
        Method to apply transfer functions between multiple components (and 
        component combinations) to produce corrected/cleaned vertical components.

        Attributes
        ----------
        correct : :class:`~obstools.atacr.classes.EventStream.CorrectDict`
            Container Dictionary for all possible corrections from the transfer functions

        """

        correct = self.CorrectDict()

        # Extract list and transfer functions available
        tf_list = tfnoise.tf_list
        transfunc = tfnoise.transfunc

        # Points in window
        ws = int(self.window/self.dt)

        # Extract traces
        trZ = Trace(); tr1 = Trace(); tr2 = Trace(); trP = Trace()
        trZ = self.sth.select(component='Z')[0]
        if self.ncomp==2 or self.ncomp==4:
            trP = self.stp[0]
        if self.ncomp==3 or self.ncomp==4:
            tr1 = self.sth.select(component='1')[0]
            tr2 = self.sth.select(component='2')[0]

        # Get Fourier spectra
        ft1 = None; ft2 = None; ftZ = None; ftP = None
        ftZ, f = utils.calculate_windowed_fft(trZ, ws, hann=False)
        if self.ncomp==2 or self.ncomp==4:
            ftP, f = utils.calculate_windowed_fft(trP, ws, hann=False)
        if self.ncomp==3 or self.ncomp==4:
            ft1, f = utils.calculate_windowed_fft(tr1, ws, hann=False)
            ft2, f = utils.calculate_windowed_fft(tr2, ws, hann=False)

        if not np.allclose(f, tfnoise.f):
            raise(Exception('Frequency axes are different: ',f, tfnoise.f))

        for key, value in tf_list.items():

            if key == 'ZP' and self.ev_list[key]:
                if value and tf_list[key]:
                    TF_ZP = transfunc[key]['TF_ZP']
                    fTF_ZP = np.hstack((TF_ZP, np.conj(TF_ZP[::-1][1:len(f)-1])))
                    corrspec = ftZ - fTF_ZP*ftP
                    corrtime = np.real(np.fft.ifft(corrspec))[0:ws]
                    correct.add('ZP', corrtime)

            if key == 'Z1' and self.ev_list[key]:
                if value and tf_list[key]:
                    TF_Z1 = transfunc[key]['TF_Z1']
                    fTF_Z1 = np.hstack((TF_Z1, np.conj(TF_Z1[::-1][1:len(f)-1])))
                    corrspec = ftZ - fTF_Z1*ft1
                    corrtime = np.real(np.fft.ifft(corrspec))[0:ws]
                    correct.add('Z1', corrtime)

            if key == 'Z2-1' and self.ev_list[key]:
                if value and tf_list[key]:
                    TF_Z1 = transfunc['Z1']['TF_Z1']
                    fTF_Z1 = np.hstack((TF_Z1, np.conj(TF_Z1[::-1][1:len(f)-1])))
                    TF_21 = transfunc[key]['TF_21']
                    fTF_21 = np.hstack((TF_21, np.conj(TF_21[::-1][1:len(f)-1])))
                    TF_Z2_1 = transfunc[key]['TF_Z2-1']
                    fTF_Z2_1 = np.hstack((TF_Z2_1, np.conj(TF_Z2_1[::-1][1:len(f)-1])))
                    corrspec = ftZ - fTF_Z1*ft1 - (ft2 - ft1*fTF_21)*fTF_Z2_1
                    corrtime = np.real(np.fft.ifft(corrspec))[0:ws]
                    correct.add('Z2-1', corrtime)

            if key == 'ZP-21' and self.ev_list[key]:
                if value and tf_list[key]:
                    TF_Z1 = transfunc[key]['TF_Z1']
                    fTF_Z1 = np.hstack((TF_Z1, np.conj(TF_Z1[::-1][1:len(f)-1])))
                    TF_21 = transfunc[key]['TF_21']
                    fTF_21 = np.hstack((TF_21, np.conj(TF_21[::-1][1:len(f)-1])))
                    TF_Z2_1 = transfunc[key]['TF_Z2-1']
                    fTF_Z2_1 = np.hstack((TF_Z2_1, np.conj(TF_Z2_1[::-1][1:len(f)-1])))
                    TF_P1 = transfunc[key]['TF_P1']
                    fTF_P1 = np.hstack((TF_P1, np.conj(TF_P1[::-1][1:len(f)-1])))
                    TF_P2_1 = transfunc[key]['TF_P2-1']
                    fTF_P2_1 = np.hstack((TF_P2_1, np.conj(TF_P2_1[::-1][1:len(f)-1])))
                    TF_ZP_21 = transfunc[key]['TF_ZP-21']
                    fTF_ZP_21 = np.hstack((TF_ZP_21, np.conj(TF_ZP_21[::-1][1:len(f)-1])))
                    corrspec = ftZ - fTF_Z1*ft1 - (ft2 - ft1*fTF_21)*fTF_Z2_1 - \
                            (ftP - ft1*fTF_P1 - (ft2 - ft1*fTF_21)*fTF_P2_1)*fTF_ZP_21
                    corrtime = np.real(np.fft.ifft(corrspec))[0:ws]
                    correct.add('ZP-21', corrtime)

            if key == 'ZH' and self.ev_list[key]:
                if value and tf_list[key]:

                    # Rotate horizontals
                    ftH = utils.rotate_dir(ft1, ft2, tfnoise.tilt)

                    TF_ZH = transfunc[key]['TF_ZH']
                    fTF_ZH = np.hstack((TF_ZH, np.conj(TF_ZH[::-1][1:len(f)-1])))
                    corrspec = ftZ - fTF_ZH*ftH
                    corrtime = np.real(np.fft.ifft(corrspec))[0:ws]
                    correct.add('ZH', corrtime)

            if key == 'ZP-H' and self.ev_list[key]:
                if value and tf_list[key]:

                    # Rotate horizontals
                    ftH = utils.rotate_dir(ft1, ft2, tfnoise.tilt)

                    TF_ZH = transfunc['ZH']['TF_ZH']
                    fTF_ZH = np.hstack((TF_ZH, np.conj(TF_ZH[::-1][1:len(f)-1])))
                    TF_PH = transfunc[key]['TF_PH']
                    fTF_PH = np.hstack((TF_PH, np.conj(TF_PH[::-1][1:len(f)-1])))
                    TF_ZP_H = transfunc[key]['TF_ZP-H']
                    fTF_ZP_H = np.hstack((TF_ZP_H, np.conj(TF_ZP_H[::-1][1:len(f)-1])))
                    corrspec = ftZ - fTF_ZH*ftH - (ftP - ftH*fTF_PH)*fTF_ZP_H
                    corrtime = np.real(np.fft.ifft(corrspec))[0:ws]
                    correct.add('ZP-H', corrtime)

        self.correct = correct


    def save(self, filename):
        """
        Method to save the object to file using `~Pickle`.

        Parameters
        ----------
        filename : str
            File name 

        """

        file = open(filename, 'wb')
        pickle.dump(self, file)
        file.close()
