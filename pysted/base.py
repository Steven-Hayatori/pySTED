
'''This module implements the essential components of a microscopy setup. By
assembling an excitation beam, a STED beam, a detector, and fluorescence
molecules, to obtain a microscope setup. The following code gives an example of
how to create such setup and use it to measure and plot the detected signal
given some ``data_model``.
    
.. code-block:: python
    
    laser_ex = base.GaussianBeam(488e-9)
    laser_sted = base.DonutBeam(575e-9, zero_residual=0.04)
    detector = base.Detector(def=0.02)
    objective = base.Objective()
    fluo = base.Fluorescence(535e-9)
    microscope = base.Microscope(laser_ex, laser_sted, detector, objective, fluo)
    
    data_map = io.read_data_map(data_model, 1)
    
    # imaging parameters
    pdt = 10e-6
    p_ex = 1e-6
    p_sted = 30e-3

    signal, _ = microscope.get_signal(data_map, 10e-9, pdt, p_ex, p_sted)
    
    from matplotlib import pyplot
    pyplot.imshow(signal)
    pyplot.colorbar()
    pyplot.show()

.. rubric:: References


.. [Deng2010] Deng, S., Liu, L., Cheng, Y., Li, R., & Xu, Z. (2010).
   Effects of primary aberrations on the fluorescence depletion patterns
   of STED microscopy. Optics Express, 18(2), 1657–1666.

.. [Garcia2000] Garcia-Parajo, M. F., Segers-Nolten, G. M. J., Veerman, J.-A-.,
   Greve, J., & Van Hulst, N. F. (2000).
   Real-time light-driven dynamics of the fluorescence emission in single green
   fluorescent protein molecules.
   Proceedings of the National Academy of Sciences, 97(13), 7237-7242.

.. [Holler2011] Höller, M. (2011).
   Advanced fluorescence fluctuation spectroscopy with pulsed
   interleaved excitation. PhD thesis, LMU, Munich (Germany).

.. [Jerker1999] Jerker, W., Ülo, M., & Rudolf, R. (1999).
   Photodynamic properties of green fluorescent proteins investigated by
   fluorescence correlation spectroscopy. Chemical Physics, 250(2), 171-186.
   
.. [Leutenegger2010] Leutenegger, M., Eggeling, C., & Hell, S. W. (2010).
    Analytical description of STED microscopy performance.
    Optics Express, 18(25), 26417–26429.

.. [RPPhoto2015] RP Photonics Consulting GmbH (Accessed 2015).
   Optical intensity. Encyclopedia of laser physics and technology at
   <https://www.rp-photonics.com/optical_intensity.html>.

.. [Staudt2009] Staudt, T. M. (2009).
   Strategies to reduce photobleaching, dark state transitions and phototoxicity
   in subdiffraction optical microscopy. Dissertation, University of Heidelberg,
   Heidelberg (Germany).

.. [Willig2006] Willig, K. I., Keller, J., Bossi, M., & Hell, S. W. (2006).
   STED microscopy resolves nanoparticle assemblies.
   New Journal of Physics, 8(6), 106.
   
.. [Xie2013] Xie, H., Liu, Y., Jin, D., Santangelo, P. J., & Xi, P. (2013).
   Analytical description of high-aperture STED resolution with 0–2pi
   vortex phase modulation.
   Journal of the Optical Society of America A (JOSA A), 30(8), 1640–1645.
'''

import numpy
import scipy.constants
import scipy.signal

# from pysted import cUtils, utils   # je dois changer ce import en les 2 autres en dessous pour que ça marche
from pysted import utils
import cUtils

# import mis par BT pour des tests
import warnings
from matplotlib import pyplot
import time


class GaussianBeam:
    '''This class implements a Gaussian beam (excitation).
    
    :param lambda_: The wavelength of the beam (m).
    :param kwargs: One or more parameters as described in the following table,
                   optional.
    
    +------------------+--------------+----------------------------------------+
    | Parameter        | Default      | Details                                |
    +==================+==============+========================================+
    | ``polarization`` | ``pi/2``     | The phase difference between :math:`x` |
    |                  |              | and :math:`y` oscillations (rad).      |
    +------------------+--------------+----------------------------------------+
    | ``beta``         | ``pi/4``     | The beam incident angle, in            |
    |                  |              | :math:`[0, \pi/2]` (rad).              |
    +------------------+--------------+----------------------------------------+
    
    Polarization :
        * :math:`\pi/2` is left-circular
        * :math:`0` is linear
        * :math:`-\pi/2` is right-circular
    '''
    
    def __init__(self, lambda_, **kwargs):
        self.lambda_ = lambda_
        self.polarization = kwargs.get("polarization", numpy.pi/2)
        self.beta = kwargs.get("beta", numpy.pi/4)
    
    # FIXME: pass Objective object instead of f, n, na, transmission
    def get_intensity(self, power, f, n, na, transmission, pixelsize, data_pixelsize=None):
        '''Compute the transmitted excitation intensity field (W/m²). The
        technique essentially follows the method described in [Xie2013]_,
        where :math:`z = 0`, along with some equations from [Deng2010]_, and
        [RPPhoto2015]_.
        
        :param power: The power of the beam (W).
        :param f: The focal length of the objective (m).
        :param n: The refractive index of the objective.
        :param na: The numerical aperture of the objective.
        :param transmission: The transmission ratio of the objective (given the
                             wavelength of the excitation beam).
        :param pixelsize: The size of an element in the intensity matrix (m).
        :returns: A 2D array.
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        def fun1(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) *\
                   scipy.special.jv(0, kr * numpy.sin(theta)) * (1 + numpy.cos(theta))
        def fun2(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta)**2 *\
                   scipy.special.jv(1, kr * numpy.sin(theta))
        def fun3(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) *\
                   scipy.special.jv(2, kr * numpy.sin(theta)) * (1 - numpy.cos(theta))
        
        alpha = numpy.arcsin(na / n)
        
        diameter = 2.233 * self.lambda_ / (na * pixelsize)
        n_pixels = int(diameter / 2) * 2 + 1 # odd number of pixels
        center = int(n_pixels / 2)
        
        # [Deng2010]
        k = 2 * numpy.pi * n / self.lambda_
        
        # compute the focal plane integrations i1 to i3 [Xie2013]
        i1 = numpy.empty((n_pixels, n_pixels))
        i2 = numpy.empty((n_pixels, n_pixels))
        i3 = numpy.empty((n_pixels, n_pixels))
        phi = numpy.empty((n_pixels, n_pixels))
        for y in range(n_pixels):
            h_rel = (center - y)
            for x in range(n_pixels):
                w_rel = (x - center)

                angle, radius = utils.cart2pol(w_rel, h_rel)
                
                kr = k * radius * pixelsize
                i1[y, x] = scipy.integrate.quad(fun1, 0, alpha, (kr,))[0]
                i2[y, x] = scipy.integrate.quad(fun2, 0, alpha, (kr,))[0]
                i3[y, x] = scipy.integrate.quad(fun3, 0, alpha, (kr,))[0]
                phi[y, x] = angle
        
        ax = numpy.sin(self.beta)
        ay = numpy.cos(self.beta) * numpy.exp(1j * self.polarization)
        
        # [Xie2013] eq. 1, where exdx = e_x, eydx = e_y, and ezdx = e_z
        exdx = -ax * 1j * (i1 + i3 * numpy.cos(2*phi))
        eydx = -ax * 1j * i3 * numpy.sin(2*phi)
        ezdx = -ax * 2 * i2 * numpy.cos(phi)
        # [Xie2013] appendix A, where exdy = e'_{1x'}, eydy = e'_{1y'}, and ezdy = e'_{1z'}
        exdy = -ay * 1j * (i1 - i3 * numpy.cos(2*phi))
        eydy = ay * 1j * i3 * numpy.sin(2*phi)
        ezdy = -ay * 2 * i2 * numpy.sin(phi)
        # [Xie2013] eq. 3
        electromagfieldx = exdx - eydy
        electromagfieldy = eydx + exdy
        electromagfieldz = ezdx + ezdy
        
        # [Xie2013] I = E_x E_x* + E_y E_y* + E_z E_z* (p. 1642)
        intensity = electromagfieldx * numpy.conj(electromagfieldx) +\
                    electromagfieldy * numpy.conj(electromagfieldy) +\
                    electromagfieldz * numpy.conj(electromagfieldz)
        
        # keep it real
        intensity = numpy.real_if_close(intensity)
        # normalize
        intensity /= numpy.max(intensity)
        
        idx_mid = int((intensity.shape[0]-1) / 2)
        r = utils.fwhm(intensity[idx_mid])
        area_fwhm = numpy.pi * (r  * pixelsize)**2 / 2
        # [RPPhoto2015]
        return intensity * 2 * transmission * power / area_fwhm

    def get_intensity_verif(self, power, f, n, na, transmission, pixelsize, data_pixelsize=None):
        '''Compute the transmitted excitation intensity field (W/m²). The
        technique essentially follows the method described in [Xie2013]_,
        where :math:`z = 0`, along with some equations from [Deng2010]_, and
        [RPPhoto2015]_.

        :param power: The power of the beam (W).
        :param f: The focal length of the objective (m).
        :param n: The refractive index of the objective.
        :param na: The numerical aperture of the objective.
        :param transmission: The transmission ratio of the objective (given the
                             wavelength of the excitation beam).
        :param pixelsize: The size of an element in the intensity matrix (m).
        :returns: A 2D array.
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        def fun1(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) * \
                   scipy.special.jv(0, kr * numpy.sin(theta)) * (1 + numpy.cos(theta))

        def fun2(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) ** 2 * \
                   scipy.special.jv(1, kr * numpy.sin(theta))

        def fun3(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) * \
                   scipy.special.jv(2, kr * numpy.sin(theta)) * (1 - numpy.cos(theta))

        alpha = numpy.arcsin(na / n)

        diameter = 2.233 * self.lambda_ / (na * pixelsize)
        n_pixels = int(diameter / 2) * 2 + 1  # odd number of pixels
        center = int(n_pixels / 2)

        # [Deng2010]
        k = 2 * numpy.pi * n / self.lambda_

        # compute the focal plane integrations i1 to i3 [Xie2013]
        i1 = numpy.empty((n_pixels, n_pixels))
        i2 = numpy.empty((n_pixels, n_pixels))
        i3 = numpy.empty((n_pixels, n_pixels))
        phi = numpy.empty((n_pixels, n_pixels))
        for y in range(n_pixels):
            h_rel = (center - y)
            for x in range(n_pixels):
                w_rel = (x - center)

                angle, radius = utils.cart2pol(w_rel, h_rel)

                kr = k * radius * pixelsize
                i1[y, x] = scipy.integrate.quad(fun1, 0, alpha, (kr,))[0]
                i2[y, x] = scipy.integrate.quad(fun2, 0, alpha, (kr,))[0]
                i3[y, x] = scipy.integrate.quad(fun3, 0, alpha, (kr,))[0]
                phi[y, x] = angle

        ax = numpy.sin(self.beta)
        ay = numpy.cos(self.beta) * numpy.exp(1j * self.polarization)

        # [Xie2013] eq. 1, where exdx = e_x, eydx = e_y, and ezdx = e_z
        exdx = -ax * 1j * (i1 + i3 * numpy.cos(2 * phi))
        eydx = -ax * 1j * i3 * numpy.sin(2 * phi)
        ezdx = -ax * 2 * i2 * numpy.cos(phi)
        # [Xie2013] appendix A, where exdy = e'_{1x'}, eydy = e'_{1y'}, and ezdy = e'_{1z'}
        exdy = -ay * 1j * (i1 - i3 * numpy.cos(2 * phi))
        eydy = ay * 1j * i3 * numpy.sin(2 * phi)
        ezdy = -ay * 2 * i2 * numpy.sin(phi)
        # [Xie2013] eq. 3
        electromagfieldx = exdx - eydy
        electromagfieldy = eydx + exdy
        electromagfieldz = ezdx + ezdy

        # [Xie2013] I = E_x E_x* + E_y E_y* + E_z E_z* (p. 1642)
        intensity = electromagfieldx * numpy.conj(electromagfieldx) + \
                    electromagfieldy * numpy.conj(electromagfieldy) + \
                    electromagfieldz * numpy.conj(electromagfieldz)

        # keep it real
        intensity = numpy.real_if_close(intensity)
        # normalize
        intensity /= numpy.max(intensity)

        idx_mid = int((intensity.shape[0] - 1) / 2)
        r = utils.fwhm(intensity[idx_mid])
        area_fwhm = numpy.pi * (r * pixelsize) ** 2 / 2
        # [RPPhoto2015]
        return intensity * 2 * transmission * power / area_fwhm


class DonutBeam:
    '''This class implements a donut beam (STED).
    
    :param lambda_: The wavelength of the beam (m).
    :param parameters: One or more parameters as described in the following
                       table, optional.
    
    +------------------+--------------+----------------------------------------+
    | Parameter        | Default      | Details                                |
    +==================+==============+========================================+
    | ``polarization`` | ``pi/2``     | The phase difference between :math:`x` |
    |                  |              | and :math:`y` oscillations (rad).      |
    +------------------+--------------+----------------------------------------+
    | ``beta``         | ``pi/4``     | The beam incident angle, in            |
    |                  |              | :math:`[0, \pi/2]` (rad).              |
    +------------------+--------------+----------------------------------------+
    | ``tau``          | ``200e-12``  | The beam pulse length (s).             |
    +------------------+--------------+----------------------------------------+
    | ``rate``         | ``80e6``     | The beam pulse rate (Hz).              |
    +------------------+--------------+----------------------------------------+
    | ``zero_residual``| ``0``        | The ratio between minimum and maximum  |
    |                  |              | intensity (ratio).                     |
    +------------------+--------------+----------------------------------------+
    
    Polarization :
        * :math:`\pi/2` is left-circular
        * :math:`0` is linear
        * :math:`-\pi/2` is right-circular
    '''
    
    def __init__(self, lambda_, **kwargs):
        self.lambda_ = lambda_
        self.polarization = kwargs.get("polarization", numpy.pi/2)
        self.beta = kwargs.get("beta", numpy.pi/4)
        self.tau = kwargs.get("tau", 200e-12)
        self.rate = kwargs.get("rate", 80e6)
        self.zero_residual = kwargs.get("zero_residual", 0)
    
    # FIXME: pass Objective object instead of f, n, na, transmission
    def get_intensity(self, power, f, n, na, transmission, pixelsize, data_pixelsize=None):
        '''Compute the transmitted STED intensity field (W/m²). The technique
        essentially follows the method described in [Xie2013]_, where
        :math:`z = 0`, along with some equations from [Deng2010]_, and
        [RPPhoto2015]_.
        
        :param power: The power of the beam (W).
        :param f: The focal length of the objective (m).
        :param n: The refractive index of the objective.
        :param na: The numerical aperture.
        :param transmission: The transmission ratio of the objective (given the
                             wavelength of the STED beam).
        :param pixelsize: The size of an element in the intensity matrix (m).
        :param data_pixelsize: The size of a pixel in the raw data matrix (m).
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        def fun1(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) *\
                   scipy.special.jv(1, kr * numpy.sin(theta)) * (1 + numpy.cos(theta))
        def fun2(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) *\
                   scipy.special.jv(1, kr * numpy.sin(theta)) * (1 - numpy.cos(theta))
        def fun3(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta) *\
                   scipy.special.jv(3, kr * numpy.sin(theta)) * (1 - numpy.cos(theta))
        def fun4(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta)**2 *\
                   scipy.special.jv(0, kr * numpy.sin(theta))
        def fun5(theta, kr):
            return numpy.sqrt(numpy.cos(theta)) * numpy.sin(theta)**2 *\
                   scipy.special.jv(2, kr * numpy.sin(theta))
        
        alpha = numpy.arcsin(na / n)
        
        diameter = 2.233 * self.lambda_ / (na * pixelsize)
        n_pixels = int(diameter / 2) * 2 + 1 # odd number of pixels
        center = int(n_pixels / 2)
        
        # [Deng2010]
        k = 2 * numpy.pi * n / self.lambda_
        
        # compute the angular integrations i1 to i5 [Xie2013]
        i1 = numpy.zeros((n_pixels, n_pixels))
        i2 = numpy.zeros((n_pixels, n_pixels))
        i3 = numpy.zeros((n_pixels, n_pixels))
        i4 = numpy.zeros((n_pixels, n_pixels))
        i5 = numpy.zeros((n_pixels, n_pixels))
        phi = numpy.zeros((n_pixels, n_pixels))
        for y in range(n_pixels):
            h_rel = (center - y)
            for x in range(n_pixels):
                w_rel = (x - center)
                
                angle, radius = utils.cart2pol(w_rel, h_rel)
                
                kr = k * radius * pixelsize
                
                i1[y, x] = scipy.integrate.quad(fun1, 0, alpha, (kr,))[0]
                i2[y, x] = scipy.integrate.quad(fun2, 0, alpha, (kr,))[0]
                i3[y, x] = scipy.integrate.quad(fun3, 0, alpha, (kr,))[0]
                i4[y, x] = scipy.integrate.quad(fun4, 0, alpha, (kr,))[0]
                i5[y, x] = scipy.integrate.quad(fun5, 0, alpha, (kr,))[0]
                phi[y, x] = angle
        
        ax = numpy.sin(self.beta)
        ay = numpy.cos(self.beta) * numpy.exp(1j * self.polarization)
        
        # [Xie2013] eq. 2, where exdx = e_x, eydx = e_y, and ezdx = e_z
        exdx = ax * (i1 * numpy.exp(1j * phi) -\
                     i2 / 2 * numpy.exp(-1j * phi) +\
                     i3 / 2 * numpy.exp(3j * phi))
        eydx = -ax * 1j / 2 * (i2 * numpy.exp(-1j * phi) +\
                               i3 * numpy.exp(3j * phi))
        ezdx = ax * 1j * (i4 - i5 * numpy.exp(2j * phi))
        
        # [Xie2013] annexe A, where exdy = e'_{2x'}, eydy = e'_{2y'}, and ezdy = e'_{2z'}
        exdy = ay * (i1 * numpy.exp(1j * phi) +\
                     i2 / 2 * numpy.exp(-1j * phi) -\
                     i3 / 2 * numpy.exp(3j * phi))
        eydy = ay * 1j / 2 * (i2 * numpy.exp(-1j * phi) +\
                              i3 * numpy.exp(3j * phi))
        ezdy = -ay * (i4 + i5 * numpy.exp(2j * phi))
        
        # [Xie2013] eq. 3
        electromagfieldx = exdx - eydy
        electromagfieldy = eydx + exdy
        electromagfieldz = ezdx + ezdy
        
        # [Xie2013] I = E_x E_x* + E_y E_y* + E_z E_z* (p. 1642)
        intensity = electromagfieldx * numpy.conj(electromagfieldx) +\
                    electromagfieldy * numpy.conj(electromagfieldy) +\
                    electromagfieldz * numpy.conj(electromagfieldz)
        
        # keep it real
        intensity = numpy.real_if_close(intensity)
        
        # normalize
        intensity /= numpy.max(intensity)
        
        # for peak intensity
        duty_cycle = self.tau * self.rate
        intensity /= duty_cycle
        
        idx_mid = int((intensity.shape[0]-1) / 2)
        r_out, r_in = utils.fwhm_donut(intensity[idx_mid])
        big_area = numpy.pi * (r_out * pixelsize)**2 / 2
        small_area = numpy.pi * (r_in * pixelsize)**2 / 2
        area_fwhm = big_area - small_area
        
        # [RPPhoto2015]
        intensity *= 2 * transmission * power / area_fwhm
        
        if power > 0:
            # zero_residual ~= min(intensity) / max(intensity)
            old_max = numpy.max(intensity)
            intensity += self.zero_residual * old_max
            intensity /= numpy.max(intensity)
            intensity *= old_max

        return intensity


class Detector:
    '''This class implements the photon detector component.
    
    :param parameters: One or more parameters as described in the following
                       table, optional.
    
    +------------------+--------------+----------------------------------------+
    | Parameter        | Default      | Details                                |
    +==================+==============+========================================+
    | ``n_airy``       | ``0.7``      | The number of airy disks used to       |
    |                  |              | compute the pinhole radius             |
    |                  |              | :math:`r_b = n_{airy} 0.61 \lambda/NA`.|
    +------------------+--------------+----------------------------------------+
    | ``noise``        | ``False``    | Whether to add poisson noise to the    |
    |                  |              | signal (boolean).                      |
    +------------------+--------------+----------------------------------------+
    | ``background``   | ``0``        | The average number of photon counts per|
    |                  |              | second due to the background [#]_.     |
    +------------------+--------------+----------------------------------------+
    | ``darkcount``    | ``0``        | The average number of photon counts per|
    |                  |              | second due to dark counts.             |
    +------------------+--------------+----------------------------------------+
    | ``pcef``         | ``0.1``      | The photon collection efficiency factor|
    |                  |              | is the ratio of emitted photons that   |
    |                  |              | could be detected (ratio).             |
    +------------------+--------------+----------------------------------------+
    | ``pdef``         | ``0.5`` [#]_ | The photon detection efficiency factor |
    |                  |              | is the ratio of collected photons that |
    |                  |              | are perceived by the detector (ratio). |
    +------------------+--------------+----------------------------------------+
    
    .. [#] The actual number is sampled from a poisson distribution with given
       mean.
    
    .. [#] Excelitas Technologies. (2011). Photon Detection Solutions.
    '''
    
    def __init__(self, **kwargs):
        # detection pinhole
        self.n_airy = kwargs.get("n_airy", 0.7)
        
        # detection noise
        self.noise = kwargs.get("noise", False)
        self.background = kwargs.get("background", 0)
        self.darkcount = kwargs.get("darkcount", 0)
        
        # photon detection
        self.pcef = kwargs.get("pcef", 0.1)
        self.pdef = kwargs.get("pdef", 0.5)
    
    def get_detection_psf(self, lambda_, psf, na, transmission, pixelsize):
        '''Compute the detection PSF as a convolution between the fluorscence
        PSF and a pinhole, as described by the equation from [Willig2006]_. The
        pinhole raidus is determined using the :attr:`n_airy`, the fluorescence
        wavelength, and the numerical aperture of the objective.
        
        :param lambda_: The fluorescence wavelength (m).
        :param psf: The fluorescence PSF that can the obtained using
                    :meth:`~pysted.base.Fluorescence.get_psf`.
        :param na: The numerical aperture of the objective.
        :param transmission: The transmission ratio of the objective for the
                             given fluorescence wavelength *lambda_*.
        :param pixelsize: The size of a pixel in the simulated image (m).
        :returns: A 2D array.
        '''
        radius = self.n_airy * 0.61 * lambda_ / na
        pinhole = utils.pinhole(radius, pixelsize, psf.shape[0])
        # convolution [Willig2006] eq. 3
        psf_det = scipy.signal.convolve2d(psf, pinhole, "same")
        # normalization to 1
        psf_det = psf_det / numpy.max(psf_det)
        return psf_det * transmission
    
    def get_signal(self, photons, dwelltime):
        '''Compute the detected signal (in photons) given the number of emitted
        photons and the time spent by the detector.
        
        :param photons: An array of number of emitted photons.
        :param dwelltime: The time spent to detect the emitted photons (s). It is
                          either a scalar or an array shaped like *nb_photons*.
        :returns: An array shaped like *nb_photons*.
        '''
        detection_efficiency = self.pcef * self.pdef # ratio
        try:
            signal = numpy.random.binomial(photons.astype(numpy.int64),
                                           detection_efficiency,
                                           photons.shape) * dwelltime
        except:
            # on Windows numpy.random.binomial cannot generate 64-bit integers
            # MARCHE PAS QUAND C'EST JUSTE UN SCALAIRE QUI EST PASSÉ
            signal = utils.approx_binomial(photons.astype(numpy.int64),
                                           detection_efficiency,
                                           photons.shape) * dwelltime
        # add noise, background, and dark counts

        if self.noise:
            signal = numpy.random.poisson(signal, signal.shape)
        if self.background > 0:
            # background counts per second
            cts = numpy.random.poisson(self.background, signal.shape)
            # background counts during dwell time
            cts = (cts * dwelltime).astype(numpy.int64)
            signal += cts
        if self.darkcount > 0:
            # dark counts per second
            cts = numpy.random.poisson(self.darkcount, signal.shape)
            # dark counts during dwell time
            cts = (cts * dwelltime).astype(numpy.int64)
            signal += cts
        return signal


class Objective:
    '''
    This class implements the microscope objective component.
    
    :param parameters: One or more parameters as described in the following
                       table, optional.
    
    +------------------+-------------------+-----------------------------------+
    | Parameter        | Default [#]_      | Details                           |
    +==================+===================+===================================+
    | ``f``            | ``2e-3``          | The objective focal length (m).   |
    +------------------+-------------------+-----------------------------------+
    | ``n``            | ``1.5``           | The refractive index.             |
    +------------------+-------------------+-----------------------------------+
    | ``na``           | ``1.4``           | The numerical aperture.           |
    +------------------+-------------------+-----------------------------------+
    | ``transmission`` | ``488: 0.84,``    | A dictionary mapping wavelengths  |
    |                  | ``535: 0.85,``    | (nm), as integer, to objective    |
    |                  | ``550: 0.86,``    | transmission factors (ratio).     |
    |                  | ``585: 0.85,``    |                                   |
    |                  | ``575: 0.85``     |                                   |
    +------------------+-------------------+-----------------------------------+
    
    .. [#] Leica 100x tube lense
    '''
    
    def __init__(self, **kwargs):
        self.f = kwargs.get("f", 2e-3)
        self.n = kwargs.get("n", 1.5)
        self.na = kwargs.get("na", 1.4)
        self.transmission = kwargs.get("transmission", {488: 0.84,
                                                        535: 0.85,
                                                        550: 0.86,
                                                        585: 0.85,
                                                        575: 0.85})
    
    def get_transmission(self, lambda_):
        return self.transmission[int(lambda_ * 1e9)]


class Fluorescence:
    '''This class implements a fluorescence molecule.
    
    :param lambda_: The fluorescence wavelength (m).
    :param parameters: One or more parameters as described in the following
                       table, optional.
    
    +------------------+--------------+----------------------------------------+
    | Parameter        | Default [#]_ | Details                                |
    +==================+==============+========================================+
    | ``sigma_ste``    |``575: 1e-21``| A dictionnary mapping STED wavelengths |
    |                  |              | as integer (nm) to stimulated emission |
    |                  |              | cross-section (m²).                    |
    +------------------+--------------+----------------------------------------+
    | ``sigma_abs``    |``488: 3e-20``| A dictionnary mapping excitation       |
    |                  |              | wavelengths as integer (nm) to         |
    |                  |              | absorption cross-section (m²).         |
    +------------------+--------------+----------------------------------------+
    | ``sigma_tri``    |``1e-21``     | The cross-section for triplet-triplet  |
    |                  |              | absorption (m²).                       |
    +------------------+--------------+----------------------------------------+
    | ``tau``          | ``3e-9``     | The fluorescence lifetime (s).         |
    +------------------+--------------+----------------------------------------+
    | ``tau_vib``      | ``1e-12``    | The vibrational relaxation (s).        |
    +------------------+--------------+----------------------------------------+
    | ``tau_tri``      | ``5e-6``     | The triplet state lifetime (s).        |
    +------------------+--------------+----------------------------------------+
    | ``qy``           | ``0.6``      | The quantum yield (ratio).             |
    +------------------+--------------+----------------------------------------+
    | ``phy_react``    | ``488: 1e-3``| A dictionnary mapping wavelengths as   |
    |                  | ``575: 1e-5``| integer (nm) to the probability of     |
    |                  |              | reaction once the molecule is in       |
    |                  |              | triplet state T_1 (ratio).             |
    +------------------+--------------+----------------------------------------+
    | ``k_isc``        | ``1e6``      | The intersystem crossing rate (s⁻¹).   |
    +------------------+--------------+----------------------------------------+
    
    .. [#] EGFP
    '''
    def __init__(self, lambda_, **kwargs):
        # psf parameters
        self.lambda_ = lambda_
        
        self.sigma_ste = kwargs.get("sigma_ste", {575: 1e-21})
        self.sigma_abs = kwargs.get("sigma_abs", {488: 3e-20})
        self.sigma_tri = kwargs.get("sigma_tri", 1e-21)
        self.tau = kwargs.get("tau", 3e-9)
        self.tau_vib = kwargs.get("tau_vib", 1e-12)
        self.tau_tri = kwargs.get("tau_tri", 5e-6)
        self.qy = kwargs.get("qy", 0.6)
        self.phy_react = kwargs.get("phy_react", {488: 1e-3, 575: 1e-5})
        self.k_isc = kwargs.get("k_isc", 0.26e6)
    
    def get_sigma_ste(self, lambda_):
        '''Return the stimulated emission cross-section of the fluorescence
        molecule given the wavelength.
        
        :param lambda_: The STED wavelength (m).
        :returns: The stimulated emission cross-section (m²).
        '''
        return self.sigma_ste[int(lambda_ * 1e9)]
        
    def get_sigma_abs(self, lambda_):
        '''Return the absorption cross-section of the fluorescence molecule
        given the wavelength.
        
        :param lambda_: The STED wavelength (m).
        :returns: The absorption cross-section (m²).
        '''
        return self.sigma_abs[int(lambda_ * 1e9)]
    
    def get_phy_react(self, lambda_):
        '''Return the reaction probability of the fluorescence molecule once it
        is in triplet state T_1 given the wavelength.
        
        :param lambda_: The STED wavelength (m).
        :returns: The probability of reaction (ratio).
        '''
        return self.phy_react[int(lambda_ * 1e9)]
    
    def get_psf(self, na, pixelsize):
        '''Compute the Gaussian-shaped fluorescence PSF.
        
        :param na: The numerical aperture of the objective.
        :param pixelsize: The size of an element in the intensity matrix (m).
        :returns: A 2D array.
        '''
        diameter = 2.233 * self.lambda_ / (na * pixelsize)
        n_pixels = int(diameter / 2) * 2 + 1 # odd number of pixels
        center = int(n_pixels / 2)
        
        fwhm = self.lambda_ / (2 * na)
        
        half_pixelsize = pixelsize / 2
        gauss = numpy.zeros((n_pixels, n_pixels))
        for y in range(n_pixels):
            h_rel = (center - y) * pixelsize
            h_lb = h_rel - half_pixelsize
            h_ub = h_rel + half_pixelsize
            for x in range(n_pixels):
                w_rel = (x - center) * pixelsize
                w_lb = w_rel - half_pixelsize
                w_ub = w_rel + half_pixelsize
                gauss[y, x] = scipy.integrate.nquad(cUtils.calculate_amplitude,
                                                    ((h_lb, h_ub), (w_lb, w_ub)),
                                                    (fwhm,))[0]
        return numpy.real_if_close(gauss / numpy.max(gauss))
    
    def get_photons(self, intensity):
        e_photon = scipy.constants.c * scipy.constants.h / self.lambda_
        return intensity // e_photon
    
    def get_k_bleach(self, lambda_, photons):
        sigma_abs = self.get_sigma_abs(lambda_)
        phy_react = self.get_phy_react(lambda_)
        T_1 = self.k_isc * sigma_abs * photons /\
                (sigma_abs * photons * (1/self.tau_tri + self.k_isc) +\
                (self.tau_tri * self.tau))
        return T_1 * photons * self.sigma_tri * phy_react


class Microscope:
    '''This class implements a microscopy setup described by an excitation beam,
    a STED (depletion) beam, a detector, some fluorescence molecules, and the
    parameters of the objective.
    
    :param excitation: A :class:`~pysted.base.GaussianBeam` object
                       representing the excitation laser beam.
    :param sted: A :class:`~pysted.base.DonutBeam` object representing the
                 STED laser beam.
    :param detector: A :class:`~pysted.base.Detector` object describing the
                     microscope detector.
    :param objective: A :class:`~pysted.base.Objective` object describing the
                      microscope objective.
    :param fluo: A :class:`~pysted.base.Fluorescence` object describing the
                 fluorescence molecules to be used.
    '''
    
    def __init__(self, excitation, sted, detector, objective, fluo):
        self.excitation = excitation
        self.sted = sted
        self.detector = detector
        self.objective = objective
        self.fluo = fluo
                
        # caching system
        self.__cache = {}
    
    def __str__(self):
        return str(self.__cache.keys())
    
    def is_cached(self, pixelsize, data_pixelsize=None):
        '''Indicate the presence of a cache entry for the given pixel size.
        
        :param pixelsize: The size of a pixel in the simulated image (m).
        :returns: A boolean.
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        pixelsize_nm = int(pixelsize * 1e9)
        return pixelsize_nm in self.__cache
    
    def cache(self, pixelsize, data_pixelsize=None):
        '''Compute and cache the excitation and STED intensities, and the
        fluorescence PSF. These intensities are computed with a power of 1 W
        such that they can serve as a basis to compute intensities with any
        power.
        
        :param pixelsize: The size of a pixel in the simulated image (m).
        :param data_pixelsize: The size of a pixel in the raw data (m)
        :returns: A tuple containing:
        
                  * A 2D array of the excitation intensity for a power of 1 W;
                  * A 2D array of the STED intensity for a a power of 1 W;
                  * A 2D array of the detection PSF.
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        pixelsize_nm = int(pixelsize * 1e9)
        if pixelsize_nm not in self.__cache:
            f, n, na = self.objective.f, self.objective.n, self.objective.na
            
            transmission = self.objective.get_transmission(self.excitation.lambda_)
            i_ex = self.excitation.get_intensity(1, f, n, na,
                                                 transmission, pixelsize, data_pixelsize)
            
            transmission = self.objective.get_transmission(self.sted.lambda_)
            i_sted = self.sted.get_intensity(1, f, n, na,
                                             transmission, pixelsize, data_pixelsize)
            
            
            transmission = self.objective.get_transmission(self.fluo.lambda_)
            psf = self.fluo.get_psf(na, pixelsize)
            psf_det = self.detector.get_detection_psf(self.fluo.lambda_, psf,
                                                      na, transmission,
                                                      pixelsize)
            self.__cache[pixelsize_nm] = utils.resize(i_ex, i_sted, psf_det)

        return self.__cache[pixelsize_nm]

    def cache_verif(self, pixelsize, data_pixelsize=None):
        '''Compute and cache the excitation and STED intensities, and the
        fluorescence PSF. These intensities are computed with a power of 1 W
        such that they can serve as a basis to compute intensities with any
        power.

        :param pixelsize: The size of a pixel in the simulated image (m).
        :param data_pixelsize: The size of a pixel in the raw data (m)
        :returns: A tuple containing:

                  * A 2D array of the excitation intensity for a power of 1 W;
                  * A 2D array of the STED intensity for a a power of 1 W;
                  * A 2D array of the detection PSF.
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        pixelsize_nm = int(pixelsize * 1e9)
        if pixelsize_nm not in self.__cache:
            f, n, na = self.objective.f, self.objective.n, self.objective.na

            transmission = self.objective.get_transmission(self.excitation.lambda_)
            i_ex = self.excitation.get_intensity_verif(1, f, n, na,
                                                       transmission, pixelsize, data_pixelsize)

            i_ex_flipped = numpy.zeros(i_ex.shape)
            i_ex_tr = i_ex[0:int(i_ex.shape[0] / 2) + 1, int(i_ex.shape[1] / 2):]
            i_ex_flipped[0:int(i_ex.shape[0] / 2) + 1, int(i_ex.shape[1] / 2):] = i_ex_tr
            i_ex_flipped[0:int(i_ex.shape[0] / 2) + 1, 0:int(i_ex.shape[1] / 2) + 1] = numpy.flip(i_ex_tr, 1)
            i_ex_flipped[int(i_ex.shape[0] / 2):, 0:int(i_ex.shape[1] / 2) + 1] = numpy.flip(i_ex_tr)
            i_ex_flipped[int(i_ex.shape[0] / 2):, int(i_ex.shape[1] / 2):] = numpy.flip(i_ex_tr, 0)

            transmission = self.objective.get_transmission(self.sted.lambda_)
            i_sted = self.sted.get_intensity(1, f, n, na,
                                             transmission, pixelsize, data_pixelsize)

            i_sted_flipped = numpy.zeros(i_sted.shape)
            i_sted_tr = i_sted[0:int(i_sted.shape[0] / 2) + 1, int(i_sted.shape[1] / 2):]
            i_sted_flipped[0:int(i_sted.shape[0] / 2) + 1, int(i_sted.shape[1] / 2):] = i_sted_tr
            i_sted_flipped[0:int(i_sted.shape[0] / 2) + 1, 0:int(i_sted.shape[1] / 2) + 1] = numpy.flip(i_sted_tr, 1)
            i_sted_flipped[int(i_sted.shape[0] / 2):, 0:int(i_sted.shape[1] / 2) + 1] = numpy.flip(i_sted_tr)
            i_sted_flipped[int(i_sted.shape[0] / 2):, int(i_sted.shape[1] / 2):] = numpy.flip(i_sted_tr, 0)

            transmission = self.objective.get_transmission(self.fluo.lambda_)
            psf = self.fluo.get_psf(na, pixelsize)
            psf_det = self.detector.get_detection_psf(self.fluo.lambda_, psf,
                                                      na, transmission,
                                                      pixelsize)

            psf_det_flipped = numpy.zeros(psf_det.shape)
            psf_det_tr = psf_det[0:int(psf_det.shape[0] / 2) + 1, int(psf_det.shape[1] / 2):]
            psf_det_flipped[0:int(psf_det.shape[0] / 2) + 1, int(psf_det.shape[1] / 2):] = psf_det_tr
            psf_det_flipped[0:int(psf_det.shape[0] / 2) + 1, 0:int(psf_det.shape[1] / 2) + 1] = numpy.flip(psf_det_tr, 1)
            psf_det_flipped[int(psf_det.shape[0] / 2):, 0:int(psf_det.shape[1] / 2) + 1] = numpy.flip(psf_det_tr)
            psf_det_flipped[int(psf_det.shape[0] / 2):, int(psf_det.shape[1] / 2):] = numpy.flip(psf_det_tr, 0)

            # self.__cache[pixelsize_nm] = utils.resize(i_ex, i_sted, psf_det)
            self.__cache[pixelsize_nm] = utils.resize(i_ex_flipped, i_sted_flipped, psf_det_flipped)

        return self.__cache[pixelsize_nm]
    
    def clear_cache(self):
        '''Empty the cache.
        
        .. important::
           It is important to empty the cache if any of the components
           :attr:`excitation`, :attr:`sted`, :attr:`detector`,
           :attr:`objective`, or :attr:`fluorescence` are internally modified
           or replaced.
        '''
        self.__cache = {}
    
    def get_effective(self, pixelsize, p_ex, p_sted, data_pixelsize=None):
        '''Compute the detected signal given some molecules disposition.
        
        :param pixelsize: The size of one pixel of the simulated image (m).
        :param p_ex: The power of the depletion beam (W).
        :param p_sted: The power of the STED beam (W).
        :param data_pixelsize: The size of one pixel of the raw data (m).
        :returns: A 2D array of the effective intensity (W) of a single molecule.
        
        The technique follows the method and equations described in
        [Willig2006]_, [Leutenegger2010]_ and [Holler2011]_.
        '''
        if data_pixelsize is None:
            data_pixelsize = pixelsize
        else:
            pixelsize = data_pixelsize

        h, c = scipy.constants.h, scipy.constants.c
        f, n, na = self.objective.f, self.objective.n, self.objective.na
        
        __i_ex, __i_sted, psf_det = self.cache(pixelsize, data_pixelsize)
        i_ex = __i_ex * p_ex
        i_sted = __i_sted * p_sted
        
        # saturation intensity (W/m²) [Leutenegger2010] p. 26419
        sigma_ste = self.fluo.get_sigma_ste(self.sted.lambda_)
        i_s = (h * c) / (self.fluo.tau * self.sted.lambda_ * sigma_ste)
        
        # [Leutenegger2010] eq. 3
        zeta = i_sted / i_s
        k_vib = 1 / self.fluo.tau_vib
        k_s1 = 1 / self.fluo.tau
        gamma = (zeta * k_vib) / (zeta * k_s1 + k_vib)
        T = 1 / self.sted.rate
        # probability of fluorescence given the donut
        eta = (((1 + gamma * numpy.exp(-k_s1 * self.sted.tau * (1 + gamma))) / (1 + gamma)) -\
              numpy.exp(-k_s1 * (gamma * self.sted.tau + T))) / (1 - numpy.exp(-k_s1 * T))
        
        # molecular brigthness [Holler2011]
        sigma_abs = self.fluo.get_sigma_abs(self.excitation.lambda_)
        excitation_probability = sigma_abs * i_ex * self.fluo.qy

        # effective intensity of a single molecule (W) [Willig2006] eq. 3
        return excitation_probability * eta * psf_det
    
    def get_signal(self, datamap, pixelsize, pdt, p_ex, p_sted, datamap_pixelsize=None, pixel_list=None):
        '''Compute the detected signal given some molecules disposition.
        
        :param datamap: A 2D array map of integers indicating how many molecules
                        are contained in each pixel of the simulated image.
        :param pixelsize: The size of one pixel of the simulated image (m).
        :param pdt: The time spent on each pixel of the simulated image (s).
        :param p_ex: The power of the excitation beam (W).
        :param p_sted: The power of the STED beam (W).
        :returns: A 2D array of the number of detected photons on each pixel.
        '''

        """# old version, does not take in count pixelsize ratio, keeping here in case
        # effective intensity across pixels (W)
        effective = self.get_effective(pixelsize, p_ex, p_sted)
        
        # stack one effective per molecule
        intensity = utils.stack(datamap, effective)
        
        photons = self.fluo.get_photons(intensity)

        return self.detector.get_signal(photons, pdt)"""

        # effective intensity across pixels (W)
        # acquisition gaussian is computed using data_pixelsize
        if datamap_pixelsize is None:
            effective = self.get_effective(pixelsize, p_ex, p_sted)
        else:
            effective = self.get_effective(datamap_pixelsize, p_ex, p_sted)

        # stack one effective per molecule
        if pixel_list is None:
            pixel_list = utils.pixel_sampling(datamap, mode="all")
        intensity = utils.stack_btmod_definitive(datamap, effective, datamap_pixelsize, pixelsize, pixel_list)

        photons = self.fluo.get_photons(intensity)

        # plante si mon acq avait un ratio autre que 1 et que pdt est un array, car les 2 matrices ne seront pas de la
        # même forme. Idée de fix 1 : juste prendre les pdt des pixels correspondants :)
        if type(pdt) is float or photons.shape == pdt.shape:
            default_returned_array = self.detector.get_signal(photons, pdt)
        else:
            ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
            new_pdt = numpy.zeros((int(numpy.ceil(pdt.shape[0] / ratio)), int(numpy.ceil(pdt.shape[1] / ratio))))
            for row in range(0, new_pdt.shape[0]):
                for col in range(0, new_pdt.shape[1]):
                    new_pdt[row, col] += pdt[row * ratio, col * ratio]
            default_returned_array = self.detector.get_signal(photons, new_pdt)

        return default_returned_array

    def get_signal_bleach_mod(self, datamap, pixelsize, pdt, p_ex, p_sted, datamap_pixelsize=None, pixel_list=None,
                              bleach=True):
        '''Compute the detected signal given some molecules disposition.

        :param datamap: A 2D array map of integers indicating how many molecules
                        are contained in each pixel of the simulated image.
        :param pixelsize: The size of one pixel of the simulated image (m).
        :param pdt: The time spent on each pixel of the simulated image (s).
        :param p_ex: The power of the excitation beam (W).
        :param p_sted: The power of the STED beam (W).
        :param bleach: Determines whether or not the laser applies bleach with each iteration. True by default.
        :returns: A 2D array of the number of detected photons on each pixel.
        ********** NOTES *************
        Cette version doit effectuer le pixel skipping comme il faut, en imaginant que la laser peut uniquement se
        déplacer sur une "grid" déterminée par le ratio entre datamap_pixelsize et pixelsize.
        Elle doit aussi appliquer le bleaching à chaque itération
        De plus, elle doit placer le résultat de l'acquisition dans le seul pixel itéré au lieu de la slice
        Finalement, l'output devrait la forme de la datamap divisé par le ratio entre les pixelsizes
        Hypothèse : Si je fais une acquisition avec un ratio de 1, cette fonction devrait me retourner le même résultat
                    que get_signal. Sinon, non, j'pense pas :) (SANS LE BLEACHING POUR CETTE HYPOTHÈSE)
        '''

        # effective intensity across pixels (W)
        # acquisition gaussian is computed using data_pixelsize
        if datamap_pixelsize is None:
            effective = self.get_effective(pixelsize, p_ex, p_sted)
        else:
            effective = self.get_effective(datamap_pixelsize, p_ex, p_sted)

        # figure out valid pixels to iterate on based on ratio between pixel sizes
        # imagine the laser is fixed on a grid, which is determined by the ratio
        valid_pixels_grid = utils.pxsize_grid(pixelsize, datamap_pixelsize, datamap)

        # if no pixel_list is passed, use valid_pixels_grid to figure out which pixels to iterate on
        # if pixel_list is passed, keep only those which are also in valid_pixels_grid
        if pixel_list is None:
            pixel_list = valid_pixels_grid
        else:
            valid_pixels_grid_matrix = numpy.zeros(datamap.shape)
            for (row, col) in valid_pixels_grid:
                valid_pixels_grid_matrix[row, col] = 1
            pixel_list_matrix = numpy.zeros(datamap.shape)
            for (row, col) in pixel_list:
                pixel_list_matrix[row, col] = 1
            final_valid_pixels_matrix = pixel_list_matrix * valid_pixels_grid_matrix
            pixel_list = numpy.argwhere(final_valid_pixels_matrix > 0)

        # prepping acquisition matrix
        ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
        datamap_rows, datamap_cols = datamap.shape
        acquired_intensity = numpy.zeros((int(numpy.ceil(datamap_rows / ratio)), int(numpy.ceil(datamap_cols / ratio))))
        h_pad, w_pad = int(effective.shape[0] / 2) * 2, int(effective.shape[1] / 2) * 2
        padded_datamap = numpy.pad(numpy.copy(datamap), h_pad // 2, mode="constant", constant_values=0).astype(int)

        # computing stuff needed to compute bleach :)
        __i_ex, __i_sted, _ = self.cache(pixelsize, data_pixelsize=datamap_pixelsize)

        photons_ex = self.fluo.get_photons(__i_ex * p_ex)
        k_ex = self.fluo.get_k_bleach(self.excitation.lambda_, photons_ex)

        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(__i_sted * p_sted * duty_cycle)
        k_sted = self.fluo.get_k_bleach(self.sted.lambda_, photons_sted)

        pad = photons_ex.shape[0] // 2 * 2
        h_size, w_size = datamap.shape[0] + pad, datamap.shape[1] + pad

        # pixeldwelltime array bull shit, À VÉRIFIER SI C'EST BON
        pixeldwelltime = numpy.asarray(pdt)
        # vérifier si pixeldwelltime est un scalaire ou une matrice, si c'est un scalaire, transformer en matrice
        if pixeldwelltime.shape == ():
            pixeldwelltime = numpy.ones(datamap.shape) * pixeldwelltime
        else:
            # live j'assume que si je passe une matrice comme pixeldwelltime, elle est de la même forme que ma datamap,
            # ajouter des trucs pour vérifier que c'est bien le cas ici :)
            verif_array = numpy.asarray([1, 2, 3])
            if type(verif_array) != type(pixeldwelltime):
                # on va tu ever se rendre ici? qq lignes plus haut je transfo pdt en array... w/e
                raise Exception("pixeldwelltime parameter must be array type")
        pdtpad = numpy.pad(pixeldwelltime, pad // 2, mode="constant", constant_values=0)

        prob_ex = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")
        prob_sted = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")

        for (row, col) in pixel_list:
            acquired_intensity[int(row / ratio), int(col / ratio)] += numpy.sum(effective *
                                                                      padded_datamap[row:row + h_pad + 1,
                                                                                     col:col + w_pad + 1])
            if bleach is True:
                # bleach stuff
                # identifier quel calcul est le plus long ici :)
                pdt_loop = pdtpad[row:row + pad + 1, col:col + pad + 1]
                prob_ex[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_ex * pdt_loop)
                prob_sted[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_sted * pdt_loop)
                prob_ex_interim = prob_ex[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
                prob_sted_interim = prob_sted[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

                padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)] = \
                    numpy.random.binomial(padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)],
                                          prob_ex_interim * prob_sted_interim)

        photons = self.fluo.get_photons(acquired_intensity)

        if type(pdt) is float or photons.shape == pdt.shape:
            default_returned_array = self.detector.get_signal(photons, pdt)
        else:
            ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
            new_pdt = numpy.zeros((int(numpy.ceil(pdt.shape[0] / ratio)), int(numpy.ceil(pdt.shape[1] / ratio))))
            for row in range(0, new_pdt.shape[0]):
                for col in range(0, new_pdt.shape[1]):
                    new_pdt[row, col] += pdt[row * ratio, col * ratio]
            default_returned_array = self.detector.get_signal(photons, new_pdt)

        return default_returned_array, padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

    def get_signal_bleach_mod2(self, datamap, pixelsize, pdt, p_ex, p_sted, datamap_pixelsize=None, pixel_list=None,
                              bleach=True):
        '''Compute the detected signal given some molecules disposition.

        :param datamap: A 2D array map of integers indicating how many molecules
                        are contained in each pixel of the simulated image.
        :param pixelsize: The size of one pixel of the simulated image (m).
        :param pdt: The time spent on each pixel of the simulated image (s).
        :param p_ex: The power of the excitation beam (W).
        :param p_sted: The power of the STED beam (W).
        :param bleach: Determines whether or not the laser applies bleach with each iteration. True by default.
        :returns: A 2D array of the number of detected photons on each pixel.
        ********** NOTES *************
        Cette version doit effectuer le pixel skipping comme il faut, en imaginant que la laser peut uniquement se
        déplacer sur une "grid" déterminée par le ratio entre datamap_pixelsize et pixelsize.
        Elle doit aussi appliquer le bleaching à chaque itération
        De plus, elle doit placer le résultat de l'acquisition dans le seul pixel itéré au lieu de la slice
        Finalement, l'output devrait la forme de la datamap divisé par le ratio entre les pixelsizes
        Hypothèse : Si je fais une acquisition avec un ratio de 1, cette fonction devrait me retourner le même résultat
                    que get_signal. Sinon, non, j'pense pas :) (SANS LE BLEACHING POUR CETTE HYPOTHÈSE)
        '''
        print("Figuring out why bleach bleaches more on top than bottom")
        # effective intensity across pixels (W)
        # acquisition gaussian is computed using data_pixelsize
        if datamap_pixelsize is None:
            effective = self.get_effective(pixelsize, p_ex, p_sted)
        else:
            effective = self.get_effective(datamap_pixelsize, p_ex, p_sted)

        # figure out valid pixels to iterate on based on ratio between pixel sizes
        # imagine the laser is fixed on a grid, which is determined by the ratio
        valid_pixels_grid = utils.pxsize_grid(pixelsize, datamap_pixelsize, datamap)

        # if no pixel_list is passed, use valid_pixels_grid to figure out which pixels to iterate on
        # if pixel_list is passed, keep only those which are also in valid_pixels_grid
        if pixel_list is None:
            pixel_list = valid_pixels_grid
        else:
            # problème avec cette méthode : ne conserve pas l'orde original de la liste
            # fine si la liste originale suit un raster scan, mais convertit tous les ordres en raster scan, ce qui
            # n'est pas fine
            # how to fix?
            # idée : avoir une autre matrice qui tient l'ordre des pixels ?
            valid_pixels_grid_matrix = numpy.zeros(datamap.shape)
            for (row, col) in valid_pixels_grid:
                valid_pixels_grid_matrix[row, col] = 1
            pixel_list_matrix = numpy.zeros(datamap.shape)
            for (row, col) in pixel_list:
                pixel_list_matrix[row, col] = 1
            final_valid_pixels_matrix = pixel_list_matrix * valid_pixels_grid_matrix
            pixel_list = numpy.argwhere(final_valid_pixels_matrix > 0)

        # prepping acquisition matrix
        ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
        datamap_rows, datamap_cols = datamap.shape
        acquired_intensity = numpy.zeros((int(numpy.ceil(datamap_rows / ratio)), int(numpy.ceil(datamap_cols / ratio))))
        h_pad, w_pad = int(effective.shape[0] / 2) * 2, int(effective.shape[1] / 2) * 2
        padded_datamap = numpy.pad(numpy.copy(datamap), (int(h_pad / 2), int(w_pad / 2)), mode="constant",
                                   constant_values=0).astype(int)

        # computing stuff needed to compute bleach :)
        __i_ex, __i_sted, psf_det = self.cache(pixelsize, data_pixelsize=datamap_pixelsize)

        #---------------------------------------------------------------------------------------------------------------

        photons_ex = self.fluo.get_photons(__i_ex * p_ex)
        k_ex = self.fluo.get_k_bleach(self.excitation.lambda_, photons_ex)

        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(__i_sted * p_sted * duty_cycle)
        k_sted = self.fluo.get_k_bleach(self.sted.lambda_, photons_sted)

        #--------------------- laser symetry verif ---------------------------------------------------------------------
        exc_upper = __i_ex[0:int(__i_ex.shape[0] / 2) + 1, :]
        exc_lower = __i_ex[int(__i_ex.shape[0] / 2):, :]
        exc_lower_flipped = numpy.flip(exc_lower, 0)
        exc_diff = exc_upper - exc_lower_flipped

        sted_upper = __i_sted[0:int(__i_sted.shape[0] / 2) + 1, :]
        sted_lower = __i_sted[int(__i_sted.shape[0] / 2):, :]
        sted_lower_flipped = numpy.flip(sted_lower, 0)
        sted_diff = sted_upper - sted_lower_flipped

        psf_upper = psf_det[0:int(psf_det.shape[0] / 2) + 1, :]
        psf_lower = psf_det[int(psf_det.shape[0] / 2):, :]
        psf_lower_flipped = numpy.flip(psf_lower, 0)
        psf_diff = psf_upper - psf_lower_flipped

        fig, axes = pyplot.subplots(2, 3)

        ex_imshow = axes[0, 0].imshow(__i_ex, interpolation="nearest")
        axes[0, 0].set_title(f"Excitation beam, shape = {__i_ex.shape}")
        fig.colorbar(ex_imshow, ax=axes[0, 0], fraction=0.04, pad=0.05)

        sted_imshow = axes[0, 1].imshow(__i_sted)
        axes[0, 1].set_title(f"STED beam, shape = {__i_sted.shape}")
        fig.colorbar(sted_imshow, ax=axes[0, 1], fraction=0.04, pad=0.05)

        psf_imshow = axes[0, 2].imshow(psf_det)
        axes[0, 2].set_title(f"PSF, shape = {psf_det.shape}")
        fig.colorbar(psf_imshow, ax=axes[0, 2], fraction=0.04, pad=0.05)

        ex_diff_imshow = axes[1, 0].imshow(exc_diff)
        axes[1, 0].set_title(f"Excitation beam symetry verif, shape = {exc_diff.shape}")
        fig.colorbar(ex_diff_imshow, ax=axes[1, 0], fraction=0.04, pad=0.05)

        sted_diff_imshow = axes[1, 1].imshow(sted_diff)
        axes[1, 1].set_title(f"STED beam symetry verif, shape = {sted_diff.shape}")
        fig.colorbar(sted_diff_imshow, ax=axes[1, 1], fraction=0.04, pad=0.05)

        psf_diff_imshow = axes[1, 2].imshow(psf_diff)
        axes[1, 2].set_title(f"PSF symetry verif, shape = {psf_diff.shape}")
        fig.colorbar(psf_diff_imshow, ax=axes[1, 2], fraction=0.04, pad=0.05)

        fig.suptitle(f"LASER SYMETRY IN bleach FUNCTION")
        pyplot.show()
        #---------------------------------------------------------------------------------------------------------------

        pad = photons_ex.shape[0] // 2 * 2
        h_size, w_size = datamap.shape[0] + pad, datamap.shape[1] + pad

        # pixeldwelltime array bull shit, À VÉRIFIER SI C'EST BON
        pixeldwelltime = numpy.asarray(pdt)
        # vérifier si pixeldwelltime est un scalaire ou une matrice, si c'est un scalaire, transformer en matrice
        if pixeldwelltime.shape == ():
            pixeldwelltime = numpy.ones(datamap.shape) * pixeldwelltime
        else:
            # live j'assume que si je passe une matrice comme pixeldwelltime, elle est de la même forme que ma datamap,
            # ajouter des trucs pour vérifier que c'est bien le cas ici :)
            verif_array = numpy.asarray([1, 2, 3])
            if type(verif_array) != type(pixeldwelltime):
                # on va tu ever se rendre ici? qq lignes plus haut je transfo pdt en array... w/e
                raise Exception("pixeldwelltime parameter must be array type")
        pdtpad = numpy.pad(pixeldwelltime, pad // 2, mode="constant", constant_values=0)

        prob_ex = numpy.pad((numpy.ones(datamap.shape)).astype(float), (int(h_pad / 2), int(w_pad / 2)),
                            mode="constant")
        prob_sted = numpy.pad((numpy.ones(datamap.shape)).astype(float), (int(h_pad / 2), int(w_pad / 2)),
                              mode="constant")

        # TESTING WHY IT BLEACHES MORE ON TOP THAN ON THE BOTTOM
        previous_iter_probs = numpy.pad((numpy.ones(datamap.shape)).astype(float), (int(h_pad / 2), int(w_pad / 2)),
                                        mode="constant")
        number_of_iters = numpy.pad((numpy.ones(datamap.shape)).astype(float), (int(h_pad / 2), int(w_pad / 2)),
                                    mode="constant")

        # video shit :)
        # video_array = numpy.ones((datamap.shape[0] + 1, datamap.shape[1]))
        # video_array[-1, :] = 0.35
        # pyplot.imshow(video_array)
        # pyplot.imshow(previous_iter_probs[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)])
        # pyplot.title(f"Survival probabilities, iterating on pixel {('NaN', 'NaN')}")
        # pyplot.colorbar()
        # pyplot.savefig(f"C:/Users/benoi/Documents/School/Automne 2020/Research_stuff/bleach_fix/week_of_14_sept/"
        #                f"flipped_laser/probabilities_evolution/un_scaled/pre_iters")
        # pyplot.close()
        # pyplot.show()

        for (row, col) in pixel_list:
            acquired_intensity[int(row / ratio), int(col / ratio)] += numpy.sum(effective *
                                                                      padded_datamap[row:row + h_pad + 1,
                                                                                     col:col + w_pad + 1])
            if bleach is True:
                # bleach stuff
                # identifier quel calcul est le plus long ici :)
                pdt_loop = pdtpad[row:row + h_pad + 1, col:col + w_pad + 1]
                prob_ex[row:row + h_pad + 1, col:col + w_pad + 1] *= numpy.exp(-k_ex * pdt_loop)
                prob_sted[row:row + h_pad + 1, col:col + w_pad + 1] *= numpy.exp(-k_sted * pdt_loop)
                prob_ex_interim = prob_ex[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
                prob_sted_interim = prob_sted[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

                padded_datamap[row:row + h_pad + 1, col:col + w_pad + 1] = \
                    numpy.random.binomial(padded_datamap[row:row + h_pad + 1, col:col + w_pad + 1],
                                          prob_ex[row:row + h_pad + 1, col:col + w_pad + 1] *
                                          prob_sted[row:row + h_pad + 1, col:col + w_pad + 1])

                # TESTING WHY IT BLEACHES MORE ON TOP THAN ON THE BOTTOM
                # print cette figure à chaque iter et la sauvegarder, faire un vid avec ça

                # si je fais previous[] = ... au lieu de *=, j'obtiens de quoi de plus symétrique
                # mais je pense pas que c'est ce je veux
                previous_iter_probs[row:row + h_pad + 1, col:col + w_pad + 1] *= \
                    prob_ex[row:row + h_pad + 1, col:col + w_pad + 1] * \
                    prob_sted[row:row + h_pad + 1, col:col + w_pad + 1]

                # previous_iter_probs[row:row + h_pad + 1, col:col + w_pad + 1] *= \
                #     numpy.exp(-k_ex * pdt_loop) * numpy.exp(-k_sted * pdt_loop)

                # padded_datamap[row:row + h_pad + 1, col:col + w_pad + 1] = \
                #     numpy.random.binomial(padded_datamap[row:row + h_pad + 1, col:col + w_pad + 1],
                #                           previous_iter_probs[row:row + h_pad + 1, col:col + w_pad + 1])

                # video_array[0:-1, :] = previous_iter_probs[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
                # pyplot.imshow(video_array)
                # pyplot.imshow(previous_iter_probs[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)])
                # pyplot.colorbar()
                # pyplot.scatter(col, row, color='r')
                # pyplot.title(f"Survival probabilities, iterating on pixel {(row, col)}")
                # pyplot.savefig(
                #     f"C:/Users/benoi/Documents/School/Automne 2020/Research_stuff/bleach_fix/week_of_14_sept/"
                #     f"flipped_laser/probabilities_evolution/un_scaled/{row}/{col}")
                # pyplot.close()
                # pyplot.show()
                number_of_iters[row:row + h_pad + 1, col:col + w_pad + 1] += 1

        # TESTING WHY IT BLEACHES MORE ON TOP THAN ON THE BOTTOM
        prob_ex_display = prob_ex[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        prob_ex_upper = prob_ex_display[0:int(prob_ex_display.shape[0] / 2), :]
        prob_ex_lower = prob_ex_display[int(prob_ex_display.shape[0] / 2):, :]
        prob_ex_lower_flipped = numpy.flip(prob_ex_lower, 0)
        diff_prob_ex = prob_ex_upper - prob_ex_lower_flipped

        prob_sted_display = prob_sted[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        prob_sted_upper = prob_sted_display[0:int(prob_sted_display.shape[0] / 2), :]
        prob_sted_lower = prob_sted_display[int(prob_sted_display.shape[0] / 2):, :]
        prob_sted_lower_flipped = numpy.flip(prob_sted_lower, 0)
        diff_prob_sted = prob_sted_upper - prob_sted_lower_flipped

        fig, axes = pyplot.subplots(2, 2)

        prob_ex_imshow = axes[0, 0].imshow(prob_ex_display)
        axes[0, 0].set_title(f"prob_ex")
        fig.colorbar(prob_ex_imshow, ax=axes[0, 0], fraction=0.04, pad=0.05)

        prob_sted_imshow = axes[0, 1].imshow(prob_sted_display)
        axes[0, 1].set_title(f"prob_sted")
        fig.colorbar(prob_sted_imshow, ax=axes[0, 1], fraction=0.04, pad=0.05)

        diff_ex_imshow = axes[1, 0].imshow(diff_prob_ex)
        axes[1, 0].set_title(f"prob_ex symetry")
        fig.colorbar(diff_ex_imshow, ax=axes[1, 0], fraction=0.04, pad=0.05)

        diff_sted_imshow = axes[1, 1].imshow(diff_prob_sted)
        axes[1, 1].set_title(f"prob_sted symetry")
        fig.colorbar(diff_sted_imshow, ax=axes[1, 1], fraction=0.04, pad=0.05)

        pyplot.show()

        # regarder les valeurs sur la première ligne de prob_Ex ou prob_sted, jsais pu quoi faire man
        print(f"{prob_sted_display[0, 0]:.30f}")
        print(f"{prob_sted_display[-1, 0]:.30f}")

        previous_iter_probs_display = previous_iter_probs[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        final_probs = prob_ex * prob_sted
        final_probs_display = final_probs[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        number_of_iters_display = number_of_iters[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

        final_upper = final_probs_display[0:int(final_probs_display.shape[0] / 2), :]
        final_lower = final_probs_display[int(final_probs_display.shape[0] / 2):, :]
        final_lower_flipped = numpy.flip(final_lower, 0)
        diff_final = final_upper - final_lower_flipped

        perceived_upper = previous_iter_probs_display[0:int(previous_iter_probs_display.shape[0] / 2), :]
        perceived_lower = previous_iter_probs_display[int(previous_iter_probs_display.shape[0] / 2):, :]
        perceived_lower_flipped = numpy.flip(perceived_lower, 0)
        diff_perceived = perceived_upper - perceived_lower_flipped

        iters_upper = number_of_iters_display[0:int(number_of_iters_display.shape[0] / 2), :]
        iters_lower = number_of_iters_display[int(number_of_iters_display.shape[0] / 2):, :]
        iters_lower_flipped = numpy.flip(iters_lower, 0)
        diff_iters = iters_upper - iters_lower_flipped

        fig, axes = pyplot.subplots(2, 3)

        final_probs_imshow = axes[0, 0].imshow(final_probs_display, interpolation="nearest")
        axes[0, 0].set_title(f"Final pixel-wise probabilities, \n"
                             f"shape = {final_probs_display.shape}")
        fig.colorbar(final_probs_imshow, ax=axes[0, 0], fraction=0.04, pad=0.05)

        perceived_probs_imshow = axes[0, 1].imshow(previous_iter_probs_display, interpolation="nearest")
        axes[0, 1].set_title(f"Perceived pixel-wise probabilities, \n"
                          f"shape = {previous_iter_probs_display.shape}")
        fig.colorbar(perceived_probs_imshow, ax=axes[0, 1], fraction=0.04, pad=0.05)

        number_imshow = axes[0, 2].imshow(number_of_iters_display, interpolation="nearest")
        axes[0, 2].set_title(f"Number of times each pixel has been sampled")
        fig.colorbar(number_imshow, ax=axes[0, 2], fraction=0.04, pad=0.05)

        diff_final_imshow = axes[1, 0].imshow(diff_final)
        axes[1, 0].set_title(f"Final probabilities symetry")
        fig.colorbar(diff_final_imshow, ax=axes[1, 0], fraction=0.04, pad=0.05)

        diff_preceived_imshow = axes[1, 1].imshow(diff_perceived, interpolation="nearest")
        axes[1, 1].set_title(f"Perceived probabilities symetry")
        fig.colorbar(diff_preceived_imshow, ax=axes[1, 1], fraction=0.04, pad=0.05)

        diff_iters_imshow = axes[1, 2].imshow(diff_iters)
        axes[1, 2].set_title(f"Number of iterations symetry")
        fig.colorbar(diff_iters_imshow, ax=axes[1, 2], fraction=0.04, pad=0.05)

        pyplot.show()

        photons = self.fluo.get_photons(acquired_intensity)

        if type(pdt) is float or photons.shape == pdt.shape:
            default_returned_array = self.detector.get_signal(photons, pdt)
        else:
            ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
            new_pdt = numpy.zeros((int(numpy.ceil(pdt.shape[0] / ratio)), int(numpy.ceil(pdt.shape[1] / ratio))))
            for row in range(0, new_pdt.shape[0]):
                for col in range(0, new_pdt.shape[1]):
                    new_pdt[row, col] += pdt[row * ratio, col * ratio]
            default_returned_array = self.detector.get_signal(photons, new_pdt)

        return default_returned_array, padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

    def get_signal_rescue(self, datamap, pixelsize, pdt, p_ex, p_sted, datamap_pixelsize=None, pixel_list=None,
                              bleach=True, rescue=False):
        '''Compute the detected signal given some molecules disposition.

        :param datamap: A 2D array map of integers indicating how many molecules
                        are contained in each pixel of the simulated image.
        :param pixelsize: The size of one pixel of the simulated image (m).
        :param pdt: The time spent on each pixel of the simulated image (s).
        :param p_ex: The power of the excitation beam (W).
        :param p_sted: The power of the STED beam (W).
        :param bleach: Determines whether or not the laser applies bleach with each iteration. True by default.
        :param rescue: Determines whether or not RESCUe acquisition mode is active. False by default
        :returns: A 2D array of the number of detected photons on each pixel.
        ********** NOTES *************
        Cette fonction est une copie de get_signal_bleach_mod avec l'ajout d'un premier essai à une implémentation du
        type d'acquisition RESCUe :)
        '''

        print("Hello World! :)")


        # effective intensity across pixels (W)
        # acquisition gaussian is computed using data_pixelsize
        if datamap_pixelsize is None:
            effective = self.get_effective(pixelsize, p_ex, p_sted)
        else:
            effective = self.get_effective(datamap_pixelsize, p_ex, p_sted)

        # figure out valid pixels to iterate on based on ratio between pixel sizes
        # imagine the laser is fixed on a grid, which is determined by the ratio
        valid_pixels_grid = utils.pxsize_grid(pixelsize, datamap_pixelsize, datamap)

        # if no pixel_list is passed, use valid_pixels_grid to figure out which pixels to iterate on
        # if pixel_list is passed, keep only those which are also in valid_pixels_grid
        if pixel_list is None:
            pixel_list = valid_pixels_grid
        else:
            valid_pixels_grid_matrix = numpy.zeros(datamap.shape)
            for (row, col) in valid_pixels_grid:
                valid_pixels_grid_matrix[row, col] = 1
            pixel_list_matrix = numpy.zeros(datamap.shape)
            for (row, col) in pixel_list:
                pixel_list_matrix[row, col] = 1
            final_valid_pixels_matrix = pixel_list_matrix * valid_pixels_grid_matrix
            pixel_list = numpy.argwhere(final_valid_pixels_matrix > 0)

        # prepping acquisition matrix
        ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
        datamap_rows, datamap_cols = datamap.shape
        acquired_intensity = numpy.zeros((int(numpy.ceil(datamap_rows / ratio)), int(numpy.ceil(datamap_cols / ratio))))
        h_pad, w_pad = int(effective.shape[0] / 2) * 2, int(effective.shape[1] / 2) * 2
        padded_datamap = numpy.pad(numpy.copy(datamap), h_pad // 2, mode="constant", constant_values=0).astype(int)

        # computing stuff needed to compute bleach :)
        __i_ex, __i_sted, _ = self.cache(pixelsize, data_pixelsize=datamap_pixelsize)

        photons_ex = self.fluo.get_photons(__i_ex * p_ex)
        k_ex = self.fluo.get_k_bleach(self.excitation.lambda_, photons_ex)

        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(__i_sted * p_sted * duty_cycle)
        k_sted = self.fluo.get_k_bleach(self.sted.lambda_, photons_sted)

        pad = photons_ex.shape[0] // 2 * 2
        h_size, w_size = datamap.shape[0] + pad, datamap.shape[1] + pad

        """# pixeldwelltime array bull shit, À VÉRIFIER SI C'EST BON
        pixeldwelltime = numpy.asarray(pdt)
        # vérifier si pixeldwelltime est un scalaire ou une matrice, si c'est un scalaire, transformer en matrice
        if pixeldwelltime.shape == ():
            pixeldwelltime = numpy.ones(datamap.shape) * pixeldwelltime
        else:
            # live j'assume que si je passe une matrice comme pixeldwelltime, elle est de la même forme que ma datamap,
            # ajouter des trucs pour vérifier que c'est bien le cas ici :)
            verif_array = numpy.asarray([1, 2, 3])
            if type(verif_array) != type(pixeldwelltime):
                # on va tu ever se rendre ici? qq lignes plus haut je transfo pdt en array... w/e
                raise Exception("pixeldwelltime parameter must be array type")
        pdtpad = numpy.pad(pixeldwelltime, pad // 2, mode="constant", constant_values=0)"""
        # Pour la fct RESCUe, ma gestion du pixeldwelltime va être différente, comme le pixeldwelltime est déterminé
        # pixel par pixel au fur et à mesure de l'acquisition
        pdt = numpy.asarray(pdt)
        if pdt.shape == ():
            # si pdt est déjà passé comme scalaire, j'utilise cette val comme max qu'on aurait
            pixeldwelltime = numpy.zeros(datamap.shape)
        else:
            # si il a passé un array, j'utilise le max de l'array comme val max qu'on aurait
            pdt_max = numpy.amax(pdt)
            pdt = pdt_max
            pixeldwelltime = numpy.zeros(datamap.shape)

        prob_ex = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")
        prob_sted = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")

        # RESCUe threshold
        centered_dot = numpy.zeros(effective.shape)
        centered_dot[int(centered_dot.shape[0] / 2), int(centered_dot.shape[1] / 2)] = 1
        single_molecule = numpy.sum(effective * centered_dot)
        single_molecule_photons = self.fluo.get_photons(single_molecule)
        single_molecule_detected_photons = self.detector.get_signal(single_molecule_photons, pdt)
        print(f"single_molecule = {single_molecule} W")
        print(f"single_molecule_photons = {single_molecule_photons} photons")
        print(f"single_molecule_detected_photons = {single_molecule_detected_photons} photons")
        print("going in da loop B)")

        for (row, col) in pixel_list:
            # JPENSE QUIL VA Y AVOIR UN IF RESCUE ICI :)

            """
            plan de match :
            Je ne suis pas trop certain de comment gérer le pdt : est-ce qu'il doit être vide initiallement?
            La meilleure idée que j'ai pour cela est d'utiliser le ratio entre le signal détecté au pixel itéré et le
            signal d'une molécule (voir ligne plus bas)
            je pense que je veux la détection d'une molécule comme threshold, ceci veut donc dire que j'utilise
            numpy.sum(effective) comme threshold. 
            Je multiplie ensuite ce ratio au pdt du pixel itéré. Par contre, le pdt pourrait être arbitraire à cette
            étape, you know?
            IL ME FAUT AUSSI UN LOWER THRESHOLD : S'IL DETECTE RIEN, JE INSTA MOVE ON, LE STED TIME EST À 0
            """


            acquired_intensity[int(row / ratio), int(col / ratio)] += numpy.sum(effective *
                                                                                padded_datamap[row:row + h_pad + 1,
                                                                                col:col + w_pad + 1])

            pdt_covered_area = numpy.ones(effective.shape)
            nb_molecs = acquired_intensity[int(row / ratio), int(col / ratio)] / single_molecule
            # bleach trop vite si j'itère sur tout, j'ai besoin d'un lower threshold pour contrer ça :)

            if nb_molecs >= 1:
                pdt_covered_area *= pdt # / nb_molecs
                pixeldwelltime[row, col] = pdt # / nb_molecs
            else:
                pdt_covered_area *= 0   # doit dépendre du pixeldwelltime
                pixeldwelltime[row, col] = 0   # ^^^^^^^^


            if bleach is True:
                # bleach stuff
                # identifier quel calcul est le plus long ici :)
                pdt_loop = pdt_covered_area
                prob_ex[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_ex * pdt_loop)
                prob_sted[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_sted * pdt_loop)
                prob_ex_interim = prob_ex[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
                prob_sted_interim = prob_sted[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

                padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)] = \
                    numpy.random.binomial(padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)],
                                          prob_ex_interim * prob_sted_interim)

        photons = self.fluo.get_photons(acquired_intensity)   # faire une version 2 de cette fonction

        if photons.shape == pixeldwelltime.shape:
            default_returned_array = self.detector.get_signal(photons, pixeldwelltime)    # ^^^^^^^^^^^^
        else:
            ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
            new_pdt = numpy.zeros((int(numpy.ceil(pixeldwelltime.shape[0] / ratio)),
                                   int(numpy.ceil(pixeldwelltime.shape[1] / ratio))))
            for row in range(0, new_pdt.shape[0]):
                for col in range(0, new_pdt.shape[1]):
                    new_pdt[row, col] += pixeldwelltime[row * ratio, col * ratio]
            pixeldwelltime = new_pdt
            default_returned_array = self.detector.get_signal(photons, pixeldwelltime)

        return default_returned_array, padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)], \
            pixeldwelltime

    def get_signal_rescue2(self, datamap, pixelsize, pdt, p_ex, p_sted, datamap_pixelsize=None, pixel_list=None,
                              bleach=True, rescue=False):
        '''Compute the detected signal given some molecules disposition.

        :param datamap: A 2D array map of integers indicating how many molecules
                        are contained in each pixel of the simulated image.
        :param pixelsize: The size of one pixel of the simulated image (m).
        :param pdt: The time spent on each pixel of the simulated image (s).
        :param p_ex: The power of the excitation beam (W).
        :param p_sted: The power of the STED beam (W).
        :param bleach: Determines whether or not the laser applies bleach with each iteration. True by default.
        :param rescue: Determines whether or not RESCUe acquisition mode is active. False by default
        :returns: A 2D array of the number of detected photons on each pixel.
        ********** NOTES *************
        Cette fonction est une copie de get_signal_bleach_mod avec l'ajout d'un premier essai à une implémentation du
        type d'acquisition RESCUe :)
        '''

        print("Dans la fonction RESCue 2 :)")
        # effective intensity across pixels (W)
        # acquisition gaussian is computed using data_pixelsize
        if datamap_pixelsize is None:
            effective = self.get_effective(pixelsize, p_ex, p_sted)
        else:
            effective = self.get_effective(datamap_pixelsize, p_ex, p_sted)

        # figure out valid pixels to iterate on based on ratio between pixel sizes
        # imagine the laser is fixed on a grid, which is determined by the ratio
        valid_pixels_grid = utils.pxsize_grid(pixelsize, datamap_pixelsize, datamap)

        # if no pixel_list is passed, use valid_pixels_grid to figure out which pixels to iterate on
        # if pixel_list is passed, keep only those which are also in valid_pixels_grid
        if pixel_list is None:
            pixel_list = valid_pixels_grid
        else:
            valid_pixels_grid_matrix = numpy.zeros(datamap.shape)
            for (row, col) in valid_pixels_grid:
                valid_pixels_grid_matrix[row, col] = 1
            pixel_list_matrix = numpy.zeros(datamap.shape)
            for (row, col) in pixel_list:
                pixel_list_matrix[row, col] = 1
            final_valid_pixels_matrix = pixel_list_matrix * valid_pixels_grid_matrix
            pixel_list = numpy.argwhere(final_valid_pixels_matrix > 0)

        # prepping acquisition matrix
        ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
        datamap_rows, datamap_cols = datamap.shape
        # acquired_intensity = numpy.zeros((int(numpy.ceil(datamap_rows / ratio)), int(numpy.ceil(datamap_cols / ratio))))
        h_pad, w_pad = int(effective.shape[0] / 2) * 2, int(effective.shape[1] / 2) * 2
        padded_datamap = numpy.pad(numpy.copy(datamap), h_pad // 2, mode="constant", constant_values=0).astype(int)

        # computing stuff needed to compute bleach :)
        __i_ex, __i_sted, _ = self.cache(pixelsize, data_pixelsize=datamap_pixelsize)

        photons_ex = self.fluo.get_photons(__i_ex * p_ex)
        k_ex = self.fluo.get_k_bleach(self.excitation.lambda_, photons_ex)

        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(__i_sted * p_sted * duty_cycle)
        k_sted = self.fluo.get_k_bleach(self.sted.lambda_, photons_sted)

        pad = photons_ex.shape[0] // 2 * 2
        h_size, w_size = datamap.shape[0] + pad, datamap.shape[1] + pad

        # Pour la fct RESCUe, ma gestion du pixeldwelltime va être différente, comme le pixeldwelltime est déterminé
        # pixel par pixel au fur et à mesure de l'acquisition
        pdt = numpy.asarray(pdt)
        if pdt.shape == ():
            # si pdt est déjà passé comme scalaire, j'utilise cette val comme max qu'on aurait
            pixeldwelltime = numpy.zeros(datamap.shape)
        else:
            # si il a passé un array, j'utilise le max de l'array comme val max qu'on aurait
            pdt_max = numpy.amax(pdt)
            pdt = pdt_max
            pixeldwelltime = numpy.zeros(datamap.shape)

        prob_ex = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")
        prob_sted = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")

        detected_photons_array = numpy.zeros(datamap.shape)

        # RESCUe threshold
        # centered_dot = numpy.zeros(effective.shape)
        # centered_dot[int(centered_dot.shape[0] / 2), int(centered_dot.shape[1] / 2)] = 1
        # single_molecule = numpy.sum(effective * centered_dot)
        # single_molecule_photons = self.fluo.get_photons(single_molecule)
        # mean_of_detected_photons = single_molecule_photons * self.detector.pcef * self.detector.pdef * pdt
        # print(f"single molecule power : {single_molecule} W")
        # print(f"single molecule emited photons : {single_molecule_photons} photons")
        # print(f"Detector detection probability = {self.detector.pcef * self.detector.pdef}")
        # print(f"mean of single molecule detected photons = {mean_of_detected_photons}")
        # print("Going into the loop :)")
        # print("Exiting :)")
        # exit()

        for (row, col) in pixel_list:
            # JPENSE QUIL VA Y AVOIR UN IF RESCUE ICI :)

            """
            plan de match :
            Je ne suis pas trop certain de comment gérer le pdt : est-ce qu'il doit être vide initiallement?
            La meilleure idée que j'ai pour cela est d'utiliser le ratio entre le signal détecté au pixel itéré et le
            signal d'une molécule (voir ligne plus bas)
            je pense que je veux la détection d'une molécule comme threshold, ceci veut donc dire que j'utilise
            numpy.sum(effective) comme threshold. 
            Je multiplie ensuite ce ratio au pdt du pixel itéré. Par contre, le pdt pourrait être arbitraire à cette
            étape, you know?
            IL ME FAUT AUSSI UN LOWER THRESHOLD : S'IL DETECTE RIEN, JE INSTA MOVE ON, LE STED TIME EST À 0
            """

            acquired_intensity = numpy.sum(effective * padded_datamap[row:row + h_pad + 1, col:col + w_pad + 1])

            pdt_covered_area = numpy.ones(effective.shape)
            emitted_photons = self.fluo.get_photons(acquired_intensity)
            detected_photons = self.detector.get_signal(emitted_photons, pdt)

            # if detected_photons >= mean_of_detected_photons:
            if detected_photons / 10 >= 1 and detected_photons <= 25:   # entre les 2 thresholds
                pdt_covered_area *= pdt
                pixeldwelltime[row, col] = pdt
            elif detected_photons > 25:   # au dessus du upper threshold
                time_for_25 = 25 * pdt / detected_photons
                pdt_covered_area *= time_for_25
                pixeldwelltime[row, col] = time_for_25
            else:   # en dessous du lower threshold
                pdt_covered_area *= pdt / 10
                pixeldwelltime[row, col] = pdt / 10
            # ajouter un elif de upper threshold? comment je le gère?

            detected_photons_array[row, col] = self.detector.get_signal(emitted_photons, pixeldwelltime[row, col])

            if bleach is True:
                # bleach stuff
                # identifier quel calcul est le plus long ici :)
                pdt_loop = pdt_covered_area
                prob_ex[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_ex * pdt_loop)
                prob_sted[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_sted * pdt_loop)
                prob_ex_interim = prob_ex[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
                prob_sted_interim = prob_sted[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]

                padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)] = \
                    numpy.random.binomial(padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)],
                                          prob_ex_interim * prob_sted_interim)

        # photons = self.fluo.get_photons(acquired_intensity)   # faire une version 2 de cette fonction
        #
        # if photons.shape == pixeldwelltime.shape:
        #     default_returned_array = self.detector.get_signal(photons, pixeldwelltime)    # ^^^^^^^^^^^^
        # else:
        #     ratio = utils.pxsize_ratio(pixelsize, datamap_pixelsize)
        #     new_pdt = numpy.zeros((int(numpy.ceil(pixeldwelltime.shape[0] / ratio)),
        #                            int(numpy.ceil(pixeldwelltime.shape[1] / ratio))))
        #     for row in range(0, new_pdt.shape[0]):
        #         for col in range(0, new_pdt.shape[1]):
        #             new_pdt[row, col] += pixeldwelltime[row * ratio, col * ratio]
        #     pixeldwelltime = new_pdt
        #     default_returned_array = self.detector.get_signal(photons, pixeldwelltime)

        return detected_photons_array, padded_datamap[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)], \
            pixeldwelltime

    def am_i_centered(self, datamap, pixelsize, pixeldwelltime, p_ex, p_sted, datamap_pixelsize, pixel_list=None):
        """
        Le but de cette fonction est de vérifier si je me centre bien sur le pixel itéré lorsque je fais mon acquisition
        / bleaching avec mes matrices de lasers superposées à mes données :)
        """
        print("VOUS ÊTES DANS LA FONCTION POUR VÉRIFIER SI VOUS ÊTES BIEN CENTRÉ :)")
        if pixel_list is None:
            print("No pixel list passed, Running a raster scan :)")
            pixel_list = utils.pixel_sampling(datamap, mode="all")
        __i_ex, __i_sted, _ = self.cache(pixelsize, data_pixelsize=datamap_pixelsize)

        photons_ex = self.fluo.get_photons(__i_ex * p_ex)
        k_ex = self.fluo.get_k_bleach(self.excitation.lambda_, photons_ex)

        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(__i_sted * p_sted * duty_cycle)
        k_sted = self.fluo.get_k_bleach(self.sted.lambda_, photons_sted)

        pad = photons_ex.shape[0] // 2 * 2
        h_size, w_size = datamap.shape[0] + pad, datamap.shape[1] + pad

        pixeldwelltime = numpy.asarray(pixeldwelltime)
        # vérifier si pixeldwelltime est un scalaire ou une matrice, si c'est un scalaire, transformer en matrice
        if pixeldwelltime.shape == ():
            pixeldwelltime = numpy.ones(datamap.shape) * pixeldwelltime
            # je devrais tu juste mettre les pixels dans pixel_list à une valeur non nulle? ce serait ce qui est ici
            """pixeldwelltime_arr = numpy.zeros(datamap.shape)
            for (row, col) in pixel_list:
                pixeldwelltime_arr[row, col] += pixeldwelltime
            pixeldwelltime = pixeldwelltime_arr"""
        else:
            # live j'assume que si je passe une matrice comme pixeldwelltime, elle est de la même forme que ma datamap,
            # ajouter des trucs pour vérifier que c'est bien le cas ici :)
            verif_array = numpy.asarray([1, 2, 3])
            if type(verif_array) != type(pixeldwelltime):
                # on va tu ever se rendre ici? qq lignes plus haut je transfo pdt en array... w/e
                raise Exception("pixeldwelltime parameter must be array type")
        pdtpad = numpy.pad(pixeldwelltime, pad // 2, mode="constant", constant_values=0)

        # à place de faire ça, je devrais faire comme je fais pour ma modif de pixelsize pour skipper certains pixels :)
        img_pixelsize_int, data_pixelsize_int = utils.pxsize_comp2(pixelsize, datamap_pixelsize)
        ratio = img_pixelsize_int / data_pixelsize_int

        traversed_array_padded = numpy.pad(datamap, pad // 2, mode="constant")
        traversed_array_roi = numpy.copy(datamap)
        acq_matrix = numpy.ones(photons_ex.shape)
        previous_pixel = None
        for (row, col) in pixel_list:
            # fait le pixel skipping comme il faut pour une liste raster scan normale, mais ne fonctionne pas pour un
            # ordre abitraire / raster inversé, need to figure out why et faire marche ça pour get_signal aussi :)
            if previous_pixel is not None:
                if row - previous_pixel[0] < ratio and col - previous_pixel[1] < ratio:   # absolues?
                    continue

            # setting up mes plots pour trouver le pixel itéré
            traversed_array_padded[row:row + pad + 1, col:col + pad + 1] += acq_matrix
            if row + pad // 2 == (row + row + pad + 1) // 2 and col + pad // 2 == (col + col + pad + 1) // 2:
                traversed_array_roi[row, col] += 1
                traversed_array_padded[(row + row + pad + 1) // 2, (col + col + pad + 1) // 2] += 1

            list_over = traversed_array_padded[row:(row + row + pad + 1) // 2, col]
            list_under = traversed_array_padded[(row + row + pad + 1) // 2 + 1:row + pad + 1, col]
            list_left = traversed_array_padded[row, col:(col + col + pad + 1) // 2]
            list_right = traversed_array_padded[row, (col + col + pad + 1) // 2 + 1:col + pad + 1]

            # plot mes shit
            fig, axes = pyplot.subplots(1, 2)

            padded_imshow = axes[0].imshow(traversed_array_padded)
            axes[0].set_title(f"Padded array, with region covered by acquisition array and original datamap highlighted"
                              f"\n"
                              f"Acquisition array shape = "
                              f"{traversed_array_padded[row:row + pad + 1, col:col + pad + 1].shape} \n"
                              f"Center of region covered by acquisition array also highlighted \n"
                              f"{len(list_over)} pixels over iterated pixel inside acquisition array, "
                              f"{len(list_under)} pixels under iterated pixel inside acquisition array, \n"
                              f"{len(list_left)} pixels left of iterated pixel inside acquisition array, "
                              f"{len(list_right)} pixels right of iterated pixel inside acquisition array")
            fig.colorbar(padded_imshow, ax=axes[0], fraction=0.04, pad=0.05)

            roi_imshow = axes[1].imshow(traversed_array_roi)
            axes[1].set_title(f"Pixel iterated over in the original datamap frame of reference")
            fig.colorbar(roi_imshow, ax=axes[1], fraction=0.04, pad=0.05)

            fig.suptitle(f'Iteration on pixel {(row, col)}', fontsize=16)

            figManager = pyplot.get_current_fig_manager()
            figManager.window.showMaximized()

            pyplot.show()

            # reverte les modifs que j'ai fait plus haut :)
            traversed_array_padded[row:row + pad + 1, col:col + pad + 1] -= 1
            if row + pad // 2 == (row + row + pad + 1) // 2 and col + pad // 2 == (col + col + pad + 1) // 2:
                traversed_array_roi[row, col] -= 1
                traversed_array_padded[(row + row + pad + 1) // 2, (col + col + pad + 1) // 2] -= 1

            previous_pixel = (row, col)

        traversed_array_padded = traversed_array_padded[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        # print(f"iterated over {counter} pixels out of {datamap.shape[0] * datamap.shape[1]}")
        return traversed_array_padded

    def bleach(self, datamap, pixelsize, pixeldwelltime, p_ex, p_sted, datamap_pixelsize, pixel_list=None):
        '''
        Compute the bleached data map using the following survival
        probability per molecule:

        .. math:: exp(-k \cdot t)

        where

        .. math::

           k = \\frac{k_{ISC} \sigma_{abs} I^2}{\sigma_{abs} I (\\tau_{triplet}^{-1} + k_{ISC}) + (\\tau_{triplet} \\tau_{fluo})} \sigma_{triplet} {phy}_{react}

        where :math:`c` is a constant, :math:`I` is the intensity, and :math:`t`
        if the pixel dwell time [Jerker1999]_ [Garcia2000]_ [Staudt2009]_.

        This version generates the lasers using datamap_pixelsize, and determines how many pixels to skip by the ratio
        between datamap_pixelsize and pixelsize.

        :param datamap: A 2D array map of integers indicating how many molecules
                        are contained in each pixel of the simulated image.
        :param pixelsize: The size of one pixel of the simulated image (m). This determines how many pixels are skipped
                          between each laser application.
        :param pixeldwelltime: The time spent on each pixel of the simulated
                               image (s).
        :param p_ex: The power of the depletion beam (W).
        :param p_sted: The power of the STED beam (W).
        :param datamap_pixelsize: The size of one pixel of the datamap. This is the resolution at which the lasers are
                                  generated.
        :param pixel_list: List of pixels on which we apply the lasers. If None is passed, a normal raster scan is done.
        :returns: A 2D array of the new data map.
        '''
        if pixel_list is None:
            print("No pixel list passed, Running a raster scan :)")
            pixel_list = utils.pixel_sampling(datamap, mode="all")
        __i_ex, __i_sted, _ = self.cache(pixelsize, data_pixelsize=datamap_pixelsize)

        photons_ex = self.fluo.get_photons(__i_ex * p_ex)
        k_ex = self.fluo.get_k_bleach(self.excitation.lambda_, photons_ex)

        duty_cycle = self.sted.tau * self.sted.rate
        photons_sted = self.fluo.get_photons(__i_sted * p_sted * duty_cycle)
        k_sted = self.fluo.get_k_bleach(self.sted.lambda_, photons_sted)

        pad = photons_ex.shape[0] // 2 * 2
        h_size, w_size = datamap.shape[0] + pad, datamap.shape[1] + pad

        pixeldwelltime = numpy.asarray(pixeldwelltime)
        # vérifier si pixeldwelltime est un scalaire ou une matrice, si c'est un scalaire, transformer en matrice
        if pixeldwelltime.shape == ():
            pixeldwelltime = numpy.ones(datamap.shape) * pixeldwelltime
        else:
            # live j'assume que si je passe une matrice comme pixeldwelltime, elle est de la même forme que ma datamap,
            # ajouter des trucs pour vérifier que c'est bien le cas ici :)
            verif_array = numpy.asarray([1, 2, 3])
            if type(verif_array) != type(pixeldwelltime):
                # on va tu ever se rendre ici? qq lignes plus haut je transfo pdt en array... w/e
                raise Exception("pixeldwelltime parameter must be array type")
        pdtpad = numpy.pad(pixeldwelltime, pad // 2, mode="constant", constant_values=0)

        # à place de faire ça, je devrais faire comme je fais pour ma modif de pixelsize pour skipper certains pixels :)
        filtered_pixel_list = utils.pixel_list_filter(datamap, pixel_list, pixelsize, datamap_pixelsize)
        prob_ex = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")
        prob_sted = numpy.pad((numpy.ones(datamap.shape)).astype(float), pad // 2, mode="constant")
        for (row, col) in filtered_pixel_list:
            pdt = pdtpad[row:row + pad + 1, col:col + pad + 1]
            prob_ex[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_ex * pdt)
            prob_sted[row:row + pad + 1, col:col + pad + 1] *= numpy.exp(-k_sted * pdt)

        datamap = datamap.astype(int)  # sinon il lance une erreur, à vérifier si c'est legit de faire ça
        prob_ex = prob_ex[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        prob_sted = prob_sted[int(pad / 2):-int(pad / 2), int(pad / 2):-int(pad / 2)]
        new_datamap = numpy.random.binomial(datamap, prob_ex * prob_sted)

        return new_datamap

    def laser_dans_face(self, datamap, pixelsize, pixeldwelltime, p_ex, p_sted, datamap_pixelsize, pixel_list=None):
        """
        Test function to see how much laser each pixel receives in the face ;)
        """
        # variable qui sera retournée, chaque pixel contiendra la quantité de photons reçus par la datamap à cause
        # des lasers
        laser_received = numpy.zeros(datamap.shape)

        # effective intensity across pixels (W)
        # acquisition gaussian is computed using data_pixelsize
        if datamap_pixelsize is None:
            print(f"datamap_pixelsize is None")
            effective = self.get_effective(pixelsize, p_ex, p_sted)
        else:
            print(f"datamap_pixelsize = {datamap_pixelsize}")
            effective = self.get_effective(datamap_pixelsize, p_ex, p_sted)

        # variable qui sera retournée, chaque pixel contiendra la quantité de photons reçus par la datamap à cause
        # des lasers
        # dans stack, on utilise data pour calculer le pad, qui est effective
        img_pixelsize_int, data_pixelsize_int = utils.pxsize_comp2(pixelsize, datamap_pixelsize)
        ratio = int(img_pixelsize_int / data_pixelsize_int)
        h_pad, w_pad = int(effective.shape[0] / 2) * 2, int(effective.shape[1] / 2) * 2
        # laser_received = numpy.zeros(
        #     (int(datamap.shape[0] / ratio) + h_pad, int(datamap.shape[1] / ratio) + w_pad))
        laser_received_pre_pad = numpy.ones(datamap.shape)
        print(f"pre pad shape = {laser_received_pre_pad.shape}")
        laser_received = numpy.pad(laser_received_pre_pad, (int(h_pad / 2), int(w_pad / 2)), 'constant',
                                   constant_values=0)   # confirmed has good shape
        laser_received_virgin = numpy.copy(laser_received)
        __i_ex, __i_sted, psf_det = self.cache_verif(pixelsize, datamap_pixelsize)

        # exc_greater_than = (__i_ex > 500000000000) * 1e13   # 1e13
        # sted_greater_than = (__i_sted > 200000000000000) * 5e14   # 5e14
        # psf_greater_than = (psf_det > 0.3) * 5
        # exc_greater_than = (__i_ex > 0) * 5   # 1e13
        # sted_greater_than = (__i_sted > 0) * 5   # 5e14
        # exc_greater_than = (__i_ex > 500000000000) * 5   # 1e13
        # sted_greater_than = (__i_sted > 200000000000000) * 5   # 5e14
        exc_greater_than = __i_ex
        sted_greater_than = __i_sted
        psf_greater_than = psf_det

        exc_upper = exc_greater_than[0:int(exc_greater_than.shape[0] / 2) + 1, :]
        exc_lower = exc_greater_than[int(exc_greater_than.shape[0] / 2):, :]
        exc_lower_flipped = numpy.flip(exc_lower, 0)
        exc_diff = exc_upper - exc_lower_flipped

        sted_upper = sted_greater_than[0:int(sted_greater_than.shape[0] / 2) + 1, :]
        sted_lower = sted_greater_than[int(sted_greater_than.shape[0] / 2):, :]
        sted_lower_flipped = numpy.flip(sted_lower, 0)
        sted_diff = sted_upper - sted_lower_flipped

        psf_upper = psf_greater_than[0:int(psf_greater_than.shape[0] / 2) + 1, :]
        psf_lower = psf_greater_than[int(psf_greater_than.shape[0] / 2):, :]
        psf_lower_flipped = numpy.flip(psf_lower, 0)
        psf_diff = psf_upper - psf_lower_flipped

        fig, axes = pyplot.subplots(2, 3)

        exc_imshow = axes[0, 0].imshow(exc_greater_than)
        axes[0, 0].set_title(f"Cte Excitation beam, shape = {exc_greater_than.shape}")
        fig.colorbar(exc_imshow, ax=axes[0, 0], fraction=0.04, pad=0.05)

        sted_imshow = axes[0, 1].imshow(sted_greater_than)
        axes[0, 1].set_title(f"Cte STED beam, shape = {sted_greater_than.shape}")
        fig.colorbar(sted_imshow, ax=axes[0, 1], fraction=0.04, pad=0.05)

        psf_imshow = axes[0, 2].imshow(psf_greater_than)
        axes[0, 2].set_title(f"Cte PSF beam, shape = {psf_greater_than.shape}")
        fig.colorbar(psf_imshow, ax=axes[0, 2], fraction=0.04, pad=0.05)

        exc_diff_imshow = axes[1, 0].imshow(exc_diff)
        axes[1, 0].set_title(f"Excitation beam, shape = {exc_diff.shape}")
        fig.colorbar(exc_diff_imshow, ax=axes[1, 0], fraction=0.04, pad=0.05)

        sted_diff_imshow = axes[1, 1].imshow(sted_diff)
        axes[1, 1].set_title(f"STED beam, shape = {sted_diff.shape}")
        fig.colorbar(sted_diff_imshow, ax=axes[1, 1], fraction=0.04, pad=0.05)

        psf_diff_imshow = axes[1, 2].imshow(psf_diff)
        axes[1, 2].set_title(f"PSF beam, shape = {psf_diff.shape}")
        fig.colorbar(psf_diff_imshow, ax=axes[1, 2], fraction=0.04, pad=0.05)

        fig.suptitle(f"DANS LA FONCTION laser_in_the_face")
        pyplot.show()
        # exit()

        # verif bullshit, to remove eventually
        iterated_pixels = numpy.zeros((int(datamap.shape[0] / ratio), int(datamap.shape[1] / ratio)))

        # VERIF SI JE SUIS BIEN CENTRÉ ???
        # mon centre devrait être 9 :)
        # COMMENT JE FAIS POUR VÉRIFIER SI JE SUIS BIEN CENTRÉ À CHAQUE ITÉRATION???
        # J'ESPÈRE QUE CE N'EST PAS ÇA LE PROBLÈME, MAIS JE NE SAIS PAS COMMENT VÉRIFIER ::))
        # slice = laser_received[0:0+h_pad+1, 0:0+w_pad+1]
        # center_row, center_col = int(slice.shape[0] / 2), int(slice.shape[1] / 2)
        # slice[center_row, center_col] = 1
        # pyplot.imshow(slice)
        # pyplot.title(f"slice shape = {slice.shape}, center pos = {(center_row, center_col)}")
        # pyplot.show()
        # exit()

        # TESTER SI C'EST MON CENTERING QUI ET LE PROBLÈME :
        # en ce moment, je pad ma datamap et je dois "shifter" mes slices pour itérer sur les bons pixels dans la
        # datamap paddée. Pour vérifier si c'est ce shifting qui cause mon problème d'asymétrie de laser reçu, je vais
        # modifier ma façon de procéder :
        # - refaire ma datamap paddée "de la bonne façon", i.e. en paddant une datamap de 1 avec des 0 sur les pads.
        # - Itérer sur TOUS les pixels de la datamap paddée. Si le pixel itéré est à 0, c'est que je suis dans le pad,
        #   donc ne rien faire. Sinon, faire le calcul normal
        # Avec cela, je m'assure de seulement itérer sur des pixels de la datamap, et sur aucun pixels du pad. Je ne
        # devrais pas avoir d'assymétrie, right? Si j'en ai, je crois que ça veut dire que mes "slices" ne sont pas
        # centrées.

        # si aucune pixel_list n'est passée, on fait un raster scan complet :)
        if pixel_list is None:
            pixel_list = utils.pixel_sampling(datamap, mode="all")
        for pixel in pixel_list:
            row = pixel[0]
            col = pixel[1]
            # 1 W = 1 J / s, donc si je multiplie par le pixeldwelltime, mon output va être en J :)
            laser_received[row:row+h_pad+1, col:col+w_pad+1] += (exc_greater_than * p_ex +
                                                                 sted_greater_than * p_sted) * pixeldwelltime
            # laser_received[row:row+h_pad+1, col:col+w_pad+1] += exc_greater_than + sted_greater_than
            iterated_pixels[row, col] = 1

        # CENTRAGE VERIF --> MON CENTRAGE EST BIEN FAIT :)
        # pixel_list = utils.pixel_sampling(laser_received, mode="all")
        # iterated_pixels = numpy.pad(iterated_pixels, (int(h_pad / 2), int(w_pad / 2)), 'constant',
        # constant_values = 0)
        # for (row, col) in pixel_list:
        #     if laser_received_virgin[row, col]:
        #         # ma slice est pas cnetrée!!!!!
        #         laser_received[row - int(h_pad / 2):row + int(h_pad / 2) + 1,
        #                        col - int(w_pad / 2):col + int(w_pad / 2) + 1] += exc_greater_than + sted_greater_than
        #         iterated_pixels[row, col] = 1

        # return laser_received[int(h_pad / 2):-int(h_pad / 2), int(w_pad / 2):-int(w_pad / 2)], iterated_pixels[int(h_pad / 2):-int(h_pad / 2), int(w_pad / 2):-int(w_pad / 2)]
        return laser_received[int(h_pad / 2):-int(h_pad / 2), int(w_pad / 2):-int(w_pad / 2)], iterated_pixels

    def laser_dans_face_2(self, datamap, pixelsize, datamap_pixelsize, pixeldwelltime, p_ex, p_sted, pixel_list=None):
        """
        2nd test function to visualize how much laser each pixel receives
        :param datamap: Datamap (array) on which the lasers will be applied.
        :param pixelsize: Grid size for the laser movement. Has to be a multiple of datamap_pixelsize. (m)
        :param datamap_pixelsize: Size of a pixel of the datamap. (m)
        :param pixeldwelltime: Time spent by the lasers on each pixel. If single value, this value will be used for each
                               pixel iterated on. If array, the according pixeldwelltime will be used for each pixel
                               iterated on.
        :param p_ex: Power of the excitation beam. (W)
        :param p_sted: Power of the STED beam. (W)
        :param pixel_list: List of pixels on which the laser will be applied. If None, a normal raster scan of every
                           pixel will be done.
        """
        pixel_list = utils.pixel_list_filter(datamap, pixel_list, pixelsize, datamap_pixelsize)

        i_ex, i_sted, psf_det = self.cache(pixelsize, datamap_pixelsize)

        laser_received, _, _ = utils.array_padder(numpy.zeros(datamap.shape), i_ex)
        sampled, rows_pad, cols_pad = utils.array_padder(numpy.zeros(datamap.shape), i_ex)

        for (row, col) in pixel_list:
            if type(pixeldwelltime) != type(laser_received):
                # tester si cette vérification fonctionne bien :)
                pixeldwelltime = numpy.ones(datamap.shape) * pixeldwelltime
            laser_applied = (i_ex * p_ex + i_sted * p_sted) * pixeldwelltime[row, col]
            sampled[row:row+2*rows_pad+1, col:col+2*cols_pad+1] += 1
            laser_received[row:row+2*rows_pad+1, col:col+2*cols_pad+1] += laser_applied

        sampled = utils.array_unpadder(sampled, i_ex)
        laser_received = utils.array_unpadder(laser_received, i_ex)

        # la fonction en tant que telle est finit, mais je serais rendu à ajouter qqchose pour traquer l'évolution
        # des coins opposés. Je crois que si j'avais de quoi de symmétrique, je m'attendrais à voir 2 listes inverses
        # l'une de l'autre, pas trop certain de ce que je m'attends dans mon cas actuel, à faire!!

        return laser_received, sampled


class Datamap:
    """This class implements a datamap

    :param molecules: The disposition of the molecules in the sample.
    :param datamap_pixelsize: The size of a pixel of the datamap
    """
    def __init__(self, molecules, datamap_pixelsize):
        self.molecules = molecules
        self.shape = molecules.shape
        self.datamap_pixelsize = datamap_pixelsize

    def show(self):
        def pix2m(x):
            return x * self.datamap_pixelsize

        def m2pix(x):
            return x / self.datamap_pixelsize

        x_size = self.shape[0] * self.datamap_pixelsize
        y_size = self.shape[1] * self.datamap_pixelsize
        fig, ax = pyplot.subplots(constrained_layout=False)
        display = ax.imshow(self.molecules, extent=[0, x_size, y_size, 0])
        ax.set_xlabel(f"Position [m]")
        ax.set_ylabel(f"Position [m]")
        ax.set_title(f"Molecule disposition, \n"
                     f"shape = {self.shape}")
        ax.ticklabel_format(axis='both', style='sci', scilimits=(0, 0))
        secxax = ax.secondary_xaxis('top', functions=(m2pix, pix2m))
        secxax.set_xlabel(f"Position [pixel]")
        secyax = ax.secondary_yaxis('right', functions=(m2pix, pix2m))
        secyax.set_ylabel(f"Position [pixel]")
        fig.colorbar(display, ax=ax, fraction=0.04, pad=0.05)
        pyplot.show()

    def add_sphere(self, width, position, max_molecs=3, randomness=1, distribution="random"):
        """
        Function to add a sphere containing molecules at a certain position
        """
        valid_distributions = ["random", "gaussian", "periphery"]
        if distribution not in valid_distributions:
            print(f"Wrong distribution choice, retard")
            print(f"Valid distributions are : ")
            for possibilites in valid_distributions:
                print(possibilites)
            raise Exception("Invalid distribution choice")

        pixels_width = utils.pxsize_ratio(width, self.datamap_pixelsize)

        # padder la datamap pour m'assurer que je puisse ajouter une sphère en périphérie de l'img aussi
        pad = pixels_width
        padded_molecules = numpy.pad(self.molecules, pad, mode="constant")

        if distribution == "random":
            for i in range(0, 360):
                x = pixels_width / 2 * numpy.cos(i * numpy.pi / 180)
                y = pixels_width / 2 * numpy.sin(i * numpy.pi / 180)

                area_covered_shape = padded_molecules[int(pad + position[0] - x): int(x + pad + position[0]),
                                                      int(y + pad + position[1])].shape
                molecs_to_place = numpy.ones(area_covered_shape[0]).astype(numpy.int) * max_molecs

                probability = randomness

                padded_molecules[int(pad + position[0] - x): int(x + pad + position[0]), int(y + pad + position[1])] = \
                    numpy.random.binomial(molecs_to_place, probability)

        elif distribution == "gaussian":
            x, y = numpy.meshgrid(numpy.linspace(-1, 1, pixels_width),
                                  numpy.linspace(-1, 1, pixels_width))
            d = numpy.sqrt(x*x+y*y)
            sigma, mu = randomness, 0.0
            g = numpy.exp(-((d-mu)**2 / (2.0 * sigma**2)))

            probabilities = numpy.zeros(padded_molecules.shape)
            probabilities[position[0] + pad // 2: position[0] + pad + pad // 2,
                          position[1] + pad // 2: position[1] + pad + pad // 2] = g

            for i in range(0, 360):
                x = pixels_width / 2 * numpy.cos(i * numpy.pi / 180)
                y = pixels_width / 2 * numpy.sin(i * numpy.pi / 180)

                area_covered_shape = padded_molecules[int(pad + position[0] - x): int(x + pad + position[0]),
                                                      int(y + pad + position[1])].shape
                molecs_to_place = numpy.ones(area_covered_shape[0]).astype(numpy.int) * max_molecs

                padded_molecules[int(pad + position[0] - x): int(x + pad + position[0]), int(y + pad + position[1])] = \
                    numpy.random.binomial(molecs_to_place,
                                          probabilities[int(pad + position[0] - x): int(x + pad + position[0]),
                                                        int(y + pad + position[1])])

        elif distribution == "periphery":
            x, y = numpy.meshgrid(numpy.linspace(-1, 1, pixels_width),
                                  numpy.linspace(-1, 1, pixels_width))
            d = numpy.sqrt(x*x+y*y)
            sigma, mu = randomness, 0.0
            g = numpy.exp(-((d-mu)**2 / (2.0 * sigma**2)))

            probabilities = numpy.zeros(padded_molecules.shape)
            probabilities[position[0] + pad // 2: position[0] + pad + pad // 2,
                          position[1] + pad // 2: position[1] + pad + pad // 2] = g
            probabilities = 1 - probabilities

            for i in range(0, 360):
                x = pixels_width / 2 * numpy.cos(i * numpy.pi / 180)
                y = pixels_width / 2 * numpy.sin(i * numpy.pi / 180)

                area_covered_shape = padded_molecules[int(pad + position[0] - x): int(x + pad + position[0]),
                                                      int(y + pad + position[1])].shape
                molecs_to_place = numpy.ones(area_covered_shape[0]).astype(numpy.int) * max_molecs

                padded_molecules[int(pad + position[0] - x): int(x + pad + position[0]), int(y + pad + position[1])] = \
                    numpy.random.binomial(molecs_to_place,
                                          probabilities[int(pad + position[0] - x): int(x + pad + position[0]),
                                                        int(y + pad + position[1])])

        # ligne pour un-pad
        self.molecules = padded_molecules[pad:-pad, pad:-pad]
