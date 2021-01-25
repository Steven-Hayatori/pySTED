
'''
This module contains utilitary functions that used across pySTED.

Code written by Benoit Turcotte, benoit.turcotte.4@ulaval.ca, October 2020
For use by FLClab (@CERVO) authorized people
'''

import numpy
import scipy, scipy.constants, scipy.integrate

# import mis par BT
import math
import random
import warnings
import tifffile

# import mis par BT pour des tests :)
from matplotlib import pyplot
import time
from pysted import temporal
from scipy.spatial.distance import cdist


def approx_binomial(n, p, size=None):
    '''Sample (64-bit) from a binomial distribution using the normal approximation.
    
    :param n: The number of trials (int or array of ints).
    :param p: The probability of success (float).
    :param size: The shape of the output (int or tuple of ints, optional).
    :returns: 64-bit int or array of 64-bit ints.
    '''
    is_0 = n == 0
    n[is_0] = 1
    gaussian = numpy.random.normal(n*p, numpy.sqrt(n*p*(1-p)), size=size)
    gaussian[is_0] = 0
    gaussian[gaussian < 0] = 0
    # add the continuity correction to sample at the midpoint of each integral bin
    gaussian += 0.5
    if size is not None:
        binomial = gaussian.astype(numpy.int64)
    else:
        # scalar
        binomial = int(gaussian)
    return binomial


def cart2pol(x, y):
    '''Convert the polar coordinates corresponding to the given cartesian
    coordinates.
    
    :param x: The :math:`x` cartesian coordinate.
    :param y: The :math:`y` cartesian coordinate.
    :returns: A tuple of the angle :math:`\\theta` and the lenght :math:`rho`.
    '''
    theta = numpy.arctan2(y, x)
    rho = numpy.sqrt(x**2 + y**2)
    return theta, rho


def complex_quadrature(func, a, b, args):
    '''Integrate a complex integrand using the Gauss-Kronrod quadrature.
    
    :param func: The function to integrate.
    :param a: The lower bound of the integration.
    :param b: The upper bound of the integration.
    :param args: Additionals arguments of the function to integrate.
    :returns: The integration result as a complex number.
    '''
    def real_func(x, args):
        return scipy.real(func(x, args))
    def imag_func(x, args):
        return scipy.imag(func(x, args))
    real_integral = scipy.integrate.quad(real_func, a, b, args)
    imag_integral = scipy.integrate.quad(imag_func, a, b, args)
    return real_integral[0] + 1j * imag_integral[0]


def fwhm(values):
    '''Compute the full width at half maximum of the Gaussian-shaped values.
    
    :param values: An array of values describing a Gaussian shape.
    :returns: The full width at half maximum.
    '''
    hm = numpy.max(values) / 2
    idx_max = numpy.argmax(values)
    for i, _ in enumerate(values[:-1]):
        if values[i+1] >= hm:
            return (idx_max - i) * 2
    raise Exception("The shape is not Gaussian, FWHM cannot be computed.")


def fwhm_donut(values):
    '''Compute the full width at half maximum of the donut-shaped values.
    
    :param values: An array of values describing a donut shape.
    :returns: A tuple of the outer and inner width at half maximum.
    '''
    hm = numpy.max(values) / 2
    idx_max = numpy.argmax(values)
    idx_min = numpy.argmin(values)
    for i, _ in enumerate(values[:-1]):
        if values[i+1] >= hm:
            # return big ray and small ray
            return idx_min - i, idx_min - (idx_max + idx_max - i)
    raise Exception("The shape of the donut is wrong, FWHM cannot be computed.")


def pinhole(radius, pixelsize, n_pixels=None):
    '''Return a pinhole mask.
    
    :param radius: The radius of the pinhole (m).
    :param pixelsize: The size of a pixel (m).
    :param n_pixels: The (optional) number of pixels (default: size of the
                     pinhole).
    '''
    if n_pixels is None:
        n_pixels = int(radius / pixelsize) * 2 + 1 # odd number of pixels
    center = int(n_pixels / 2)
    # n_pixels x n_pixels arrays containing the x and y coordinates as values
    xx, yy = numpy.mgrid[:n_pixels, :n_pixels]
    # a circle is the squared distance to the center point
    circle = numpy.sqrt((xx - center)**2 + (yy - center)**2)
    return (circle <= radius / pixelsize)


def rescale(data, factor):
    '''Rescale the *data* container (and content) given the ratio between the
    current container unit size and the new container unit size.
    
    
    Example::
    
        >>> data_10nm = numpy.array([[1, 0, 0, 0],
                                     [0, 1, 0, 0],
                                     [0, 0, 0, 0],
                                     [0, 0, 0, 0]])
        >>> rescale(data_10nm, 2) # rescale to 20 nm size
        numpy.array([[2, 0],
                     [0, 0]])
    
    :param data: A 2D array.
    :param factor: The ratio between the original container units and the new
                   container units.
    :returns: A 2D array.
    '''
    assert factor > 0, "The rescale factor must be positive!"
    new_data_h = int(data.shape[0] // factor)
    new_data_w = int(data.shape[1] // factor)
    new_data = numpy.zeros((new_data_h, new_data_w), dtype=data.dtype)
    for y in range(new_data_h):
        y_old_start = int(y * factor)
        y_old_end = int(y_old_start + factor) 
        for x in range(new_data_w):
            x_old_start = int(x * factor)
            x_old_end = int(x_old_start + factor)
            new_data[y, x] = numpy.sum(data[y_old_start:y_old_end,
                                            x_old_start:x_old_end])
    return new_data


def resize(*images):
    '''Resize images to the shape of the largest (pad with zeros).
    
    :param images: Square shaped images.
    :returns: A tuple of copies of the given *images* resized to the size of the
              largest input image.
    '''
    def fit(small_image, large_image):
        '''Pad with zeros and return a small image to fit a larger image,
        assuming square shaped images.
        '''
        half_small = int(small_image.shape[0] / 2)
        half_large = int(large_image.shape[0] / 2)
        pad = half_large - half_small
        return numpy.pad(small_image, ((pad, pad), (pad, pad)), "constant")
    
    sizes = [image.shape[0] for image in images]
    idx = numpy.argmax(sizes)
    largest_image = images[idx]
    new_images = [fit(image, largest_image) if i != idx else largest_image
                  for i, image in enumerate(images)]
    return tuple(new_images)


def inverse(x, a=1):
    '''Evaluate the inverse function :math:`1 / (a x + 1)`.
    
    :param x: An integer or array.
    :param a: The scale of *x*.
    :returns: The result of the function, same shape as *x*.
    '''
    return 1 / (a * x + 1)


def inverse_exponential(x, a=1):
    '''Evaluate the inverse function :math:`1 / e^{ax}`.
    
    :param x: An integer or array.
    :param a: The scale of *x*.
    :returns: The result of the function, same shape as *x*.
    '''
    return 1 / (numpy.exp(a * x))


def exponential(x, a):
    return numpy.exp(-a * x)


def stack(datamap, data):
    '''Compute a new frame consisting in a replication of the given *data*
    centered at every positions and multiplied by the factors given in the
    *datamap*.
    
    Example::
    
        >>> datamap = numpy.array([[2, 0, 0, 0],
                                   [0, 0, 0, 0],
                                   [0, 0, 0, 0],
                                   [0, 0, 0, 0]])
        >>> data = numpy.array([[1, 2, 1],
                                [2, 3, 2],
                                [1, 2, 1]])
        >>> utils.stack(datamap, data)
        numpy.array([[6, 4, 0, 0],
                     [4, 2, 0, 0],
                     [0, 0, 0, 0],
                     [0, 0, 0, 0]])
    
    :param datamap: A 2D array indicating how many data are positioned in every
    :param data: A 2D array containing the data to replicate.
    :returns: A 2D array shaped like *datamap*.
    *** EN DATE DU 23/09 CETTE FONCTION N'EST PAS UTILISÉE NUL PART ***
    *** JE VAIS TOUT DE MÊME LA GARDER, CAR C'EST LA RÉFÉRENCE ORIGINALES POUR TOUTES LES FONCTIONS STACK ***
    '''
    h_pad, w_pad = int(data.shape[0] / 2) * 2, int(data.shape[1] / 2) * 2
    frame = numpy.zeros((datamap.shape[0] + h_pad, datamap.shape[1] + w_pad))
    positions = numpy.where(datamap > 0)
    numbers = datamap[positions]
    for nb, y, x in zip(numbers, *positions):
        frame[y:y+h_pad+1, x:x+w_pad+1] += data * nb
    return frame[int(h_pad/2):-int(h_pad/2), int(w_pad/2):-int(w_pad/2)]


def stack_btmod_definitive(datamap, data, data_pixelsize, img_pixelsize, pixel_list):
    '''Compute a new frame consisting in a replication of the given *data*
    centered at every positions and multiplied by the factors given in the
    *datamap*.

    Example::

        >>> datamap = numpy.array([[2, 0, 0, 0],
                                   [0, 0, 0, 0],
                                   [0, 0, 0, 0],
                                   [0, 0, 0, 0]])
        >>> data = numpy.array([[1, 2, 1],
                                [2, 3, 2],
                                [1, 2, 1]])
        >>> utils.stack(datamap, data)
        numpy.array([[6, 4, 0, 0],
                     [4, 2, 0, 0],
                     [0, 0, 0, 0],
                     [0, 0, 0, 0]])

    :param datamap: A 2D array indicating how many data are positioned in every
    :param data: A 2D array containing the data to replicate.
    :param data_pixelsize: Length of a pixel in the datamap (m)
    :param img_pixelsize: Distance the laser moves in between each application of data. Must be a multiple of the
                          data_pixelsize (m)
    :param pixel_list: List of pixels on which we want to do the acquisition.
    :returns: A 2D array shaped like *datamap*.
    *** CALLED ONCE IN microscope.get_signal WHEN A PIXEL LIST IS PASSED (23/09) ***
    '''
    filtered_pixel_list = pixel_list_filter(datamap, pixel_list, img_pixelsize, data_pixelsize)
    h_pad, w_pad = int(data.shape[0] / 2) * 2, int(data.shape[1] / 2) * 2
    modif_returned_array = numpy.zeros((datamap.shape[0] + h_pad, datamap.shape[1] + w_pad))
    padded_datamap = numpy.pad(numpy.copy(datamap), h_pad // 2, mode="constant", constant_values=0)

    for (row, col) in filtered_pixel_list:
        modif_returned_array[row:row + h_pad + 1, col:col + w_pad + 1] += data * padded_datamap[row:row + h_pad + 1,
                                                                                                col:col + w_pad + 1]

        # modif_returned_array[row:row + h_pad + 1, col:col + w_pad + 1] += data * datamap[row, col]
    return modif_returned_array[int(h_pad / 2):-int(h_pad / 2), int(w_pad / 2):-int(w_pad / 2)]


def pixel_sampling(datamap, mode="all"):
    '''
    Function to test different pixel sampling methods, instead of simply imaging pixel by pixel
    :param datamap: A 2D array of the data to be imaged, used for its shape.
    :param mode: A keyword to determine the order of pixels in the returned list. By default, all pixels are added in a
                 raster scan (left to right, row by row) order.
    :returns: A list containing all the pixels in the order in which we want them to be imaged.
    '''
    pixel_list = []
    if mode == "all":
        for row in range(datamap.shape[0]):
            for col in range(datamap.shape[1]):
                pixel_list.append((row, col))
    elif mode == "checkers":
        # TODO: ajouter checker_size comme param au lieu de hard codé ici
        # TODO: regarder s'il y a une manière plus efficace de faire ça
        checkers = numpy.zeros((datamap.shape[0], datamap.shape[1]))
        cell_size = 100

        even_row = True
        cell_white = False
        for row in range(0, checkers.shape[0], cell_size):
            for col in range(0, checkers.shape[0], cell_size):
                cell_white = not cell_white
                if even_row:
                    if cell_white:
                        checkers[row:row + cell_size, col: col + cell_size] = 1
                if not even_row:
                    if not cell_white:
                        checkers[row:row + cell_size, col: col + cell_size] = 1
            even_row = not even_row

        for row in range(datamap.shape[0]):
            for col in range(datamap.shape[1]):
                if checkers[row, col] == 1:
                    pixel_list.append((row, col))
    elif mode == "forsenCD":
        positions = numpy.where(datamap > 0)
        pixel_list = list(zip(positions[0], positions[1]))
    elif mode == "besides":
        pixel_list = []
        positions = numpy.where(datamap > 0)
        molecules = list(zip(positions[0], positions[1]))
        padded_datamap = numpy.pad(numpy.zeros(datamap.shape), 1, mode="constant")
        verif_matrix = numpy.zeros(datamap.shape)
        for (row, col) in molecules:
            interim_pixel_list = []
            xd = numpy.where(datamap[row-1:row+2, col-1:col+2] == 0)
            interim_pixel_list.append(list(zip(xd[0], xd[1])))
            interim_pixel_list = interim_pixel_list[0]
            for pixel in interim_pixel_list:
                if verif_matrix[pixel[0] + row - 1, pixel[1] + col - 1] == 0:
                    pixel_list.append((pixel[0] + row - 1, pixel[1] + col - 1))
                verif_matrix[pixel[0] + row - 1, pixel[1] + col - 1] = 1
    else:
        print(f"list_mode = {mode} is not valid, retard")

    return pixel_list


def pxsize_comp2(img_pixelsize, data_pixelsize):
    """
    Try number 2 for my float comparison function that hopefully will give the right values this time :)
    :param img_pixelsize: Acquisition pixel size. Has to be a multiple of data_pixelsize (m).
    :param data_pixelsize: Raw data pixelsize (m).
    :returns: Integer values of the pixelsizes which can later be used to compute ratios and stuff :)
    """
    # test = img_pixelsize / data_pixelsize
    # test_int = int(img_pixelsize / data_pixelsize)
    # test3 = img_pixelsize % data_pixelsize
    # if img_pixelsize < data_pixelsize or not math.isclose(test3, 0):
    #     raise Exception("img_pixelsize has to be a multiple of data_pixelsize")
    img_pixelsize_int = float(str(img_pixelsize)[0: str(img_pixelsize).find('e')])
    data_pixelsize_int = float(str(data_pixelsize)[0: str(data_pixelsize).find('e')])
    img_pixelsize_exp = int(str(img_pixelsize)[str(img_pixelsize).find('e') + 1:])
    data_pixelsize_exp = int(str(data_pixelsize)[str(data_pixelsize).find('e') + 1:])
    exp = img_pixelsize_exp - data_pixelsize_exp
    img_pixelsize_int *= 10 ** exp
    # img_pixelsize_int = int(img_pixelsize_int)
    # data_pixelsize_int = int(data_pixelsize_int)
    test3 = img_pixelsize_int % data_pixelsize_int
    if img_pixelsize < data_pixelsize or not math.isclose(test3, 0):
        raise Exception("img_pixelsize has to be a multiple of data_pixelsize")
    return img_pixelsize_int, data_pixelsize_int


def pxsize_comp_array_maker(img_pixelsize, data_pixelsize, datamap):
    """
    Function which utilizes the ratio between the image pixelsize and the datamap pixelsize to create an appropriatly
    sized output datamap for a normal raster scan acquisition with ratio jumps between laser applications. This assures
    that the laser application is placed in the appropriate acquisition output pixel.
    :param img_pixelsize: The image pixelsize (m)
    :param data_pixelsize: The datamap pixelsize (m)
    :param datamap: The datamap on which the acquisition is made
    :returns: An empty datamap of shape (ceil(datamap.shape[0] / ratio), ceil(datamap.shape[1] / ratio))
    """
    img_pixelsize_int, data_pixelsize_int = pxsize_comp2(img_pixelsize, data_pixelsize)
    ratio = img_pixelsize_int / data_pixelsize_int
    nb_rows = int(numpy.ceil(datamap.shape[0] / ratio))
    nb_cols = int(numpy.ceil(datamap.shape[1] / ratio))
    datamap_to_fill = numpy.zeros((nb_rows, nb_cols))
    return datamap_to_fill


def pxsize_grid(img_pixelsize, data_pixelsize, datamap):
    """
    Function which creates a grid of the pixels which can be iterated on based on the ratio between img_pixelsize and
    data_pixelsize. Imagine the laser is fixed on a grid and can only make discrete movements, and this grid size is
    determined by the ratio
    :param img_pixelsize: Size of the minimum distance the laser must do between acquisitions (m). Must be a multiple of
                          data_pixelsize.
    :param data_pixelsize: Size of a pixel of the datamap (m).
    :param datamap: Raw molecule dispotion on which we wish to do an acquisition.
    :returns: A list of the pixels which can be iterated on (?)
    """
    img_pixelsize_int, data_pixelsize_int = pxsize_comp2(img_pixelsize, data_pixelsize)
    ratio = int(img_pixelsize_int / data_pixelsize_int)

    valid_pixels = []
    for row in range(0, datamap.shape[0], ratio):
        for col in range(0, datamap.shape[1], ratio):
            valid_pixels.append((row, col))

    return valid_pixels


def pxsize_ratio(img_pixelsize, data_pixelsize):
    """
    Computes the ratio between the acquisition pixel size and the datamap pixel size
    :param img_pixelsize: Minimum distance the laser must move during application. Multiple of data_pixelsize (m).
    :param data_pixelsize: Size of a pixel in the datamap (m).
    :returns: the ratio between pixel sizes
    """
    img_pixelsize_int, data_pixelsize_int = pxsize_comp2(img_pixelsize, data_pixelsize)
    ratio = int(img_pixelsize_int / data_pixelsize_int)
    return ratio


def mse_calculator(array1, array2):
    """
    Compute the RMS between two arrays. Must be of same size
    :param array1: First array
    :param array2: Second array
    :returns: Mean squarred error of the 2 arrays
    """
    # jpourrais mettre un ti qqchose ici pour vérifier si les 2 arrays ont la même forme, jsp si c'est nécessaire
    array_diff = numpy.absolute(array1 - array2)
    array_diff_squared = numpy.square(array_diff)
    mean_squared_error = float(numpy.sum(array_diff_squared) / (array1.shape[0] * array1.shape[1]))
    return mean_squared_error


def pixel_list_filter(datamap, pixel_list, img_pixelsize, data_pixelsize):
    """
    Function to pre-filter a pixel list. Depending on the ratio between the data_pixelsize and acquisition pixelsize,
    a certain number of pixels must be skipped between laser applications.
    :param pixel_list: The list of pixels passed to the acquisition function, which needs to be filtered
    :param img_pixelsize: The acquisition pixelsize (m)
    :param data_pixelsize: The data pixelsize (m)
    :returns: A filtered version of the input pixel_list, from which the pixels which can't be iterated over due to the
              pixel sizes have been removed
    """
    # figure out valid pixels to iterate on based on ratio between pixel sizes
    # imagine the laser is fixed on a grid, which is determined by the ratio
    valid_pixels_grid = pxsize_grid(img_pixelsize, data_pixelsize, datamap)

    # if no pixel_list is passed, use valid_pixels_grid to figure out which pixels to iterate on
    # if pixel_list is passed, keep only those which are also in valid_pixels_grid
    if pixel_list is None:
        pixel_list = valid_pixels_grid
    else:
        valid_pixels_grid_matrix = numpy.zeros(datamap.shape)
        nb_valid_pixels = 0
        for (row, col) in valid_pixels_grid:
            valid_pixels_grid_matrix[row, col] = 1
            nb_valid_pixels += 1
        pixel_list_matrix = numpy.zeros(datamap.shape)
        order = 1
        for (row, col) in pixel_list:
            pixel_list_matrix[row, col] = order
            order += 1
        final_valid_pixels_matrix = pixel_list_matrix * valid_pixels_grid_matrix
        if numpy.array_equal(final_valid_pixels_matrix, numpy.zeros(datamap.shape)):
            warnings.warn(" \nNo pixels in the list passed is valid given the ratio between pixel sizes, \n"
                          "Iterating on valid pixels in a raster scan instead.")
            pixel_list = valid_pixels_grid  # itérer sur les pixels valides seulement
        else:
            pixel_list_interim = numpy.argsort(final_valid_pixels_matrix, axis=None)
            pixel_list_interim = numpy.unravel_index(pixel_list_interim, datamap.shape)
            pixel_list = [(pixel_list_interim[0][i], pixel_list_interim[1][i])
                          for i in range(len(pixel_list_interim[0]))]
            pixel_list = pixel_list[-numpy.count_nonzero(final_valid_pixels_matrix):]

    return pixel_list


def symmetry_verifier(array, direction="vertical", plot=False):
    """
    Verifies if the given array is symmetrical along the vertical or horizontal direction
    :param array: Array to be verified for symmetry
    :param direction: Direction along which to verify the symmetry. Vertical to see upper vs lower half, Horizontal to
                      see left vs right half.
    :param plot: Determines whether or not graphs of array and its symmetry will be displayed.
    :returns: Array(s) displaying the symmetry
    """

    direction_lc = direction.lower()
    valid_directions = ["vertical", "horizontal"]
    if direction_lc not in valid_directions:
        raise Exception(f"{direction} is not a valid direction, valid directions are {valid_directions}")

    nb_rows, nb_cols = array.shape
    if direction_lc == "vertical":
        if nb_rows % 2 == 0:
            halfway = nb_rows // 2
            upper_half = array[0:halfway, :]
            lower_half = array[halfway:, :]
        else:
            halfway = nb_rows // 2 + 1
            upper_half = array[0:halfway, :]
            lower_half = array[halfway - 1:, :]
        symmetry = upper_half - numpy.flip(lower_half, 0)
    elif direction_lc == "horizontal":
        if nb_cols % 2 == 0:
            halfway = nb_cols // 2
            left_half = array[:, 0:halfway]
            right_half = array[:, halfway:]
        else:
            halfway = nb_cols // 2 + 1
            left_half = array[:, 0:halfway]
            right_half = array[:, halfway - 1:]
        symmetry = left_half - numpy.flip(right_half, 1)
    else:
        # forbidden zone, shouldn't go there ever because of previous error handling
        raise Exception(f"Forbidden zone, call BT if you get here")

    if plot:
        fig, axes = pyplot.subplots(1, 2)

        base_imshow = axes[0].imshow(array)
        axes[0].set_title(f"Base input array")
        fig.colorbar(base_imshow, ax=axes[0], fraction=0.04, pad=0.05)

        symmetry_imshow = axes[1].imshow(symmetry)
        axes[1].set_title(f"{direction_lc.capitalize()} symmetry verification")
        fig.colorbar(symmetry_imshow, ax=axes[1], fraction=0.04, pad=0.05)

        pyplot.show()

    return symmetry


def array_padder(base, laser, pad_value=0):
    """
    Function used to pad an array (base) according to the size of the secondary array being iterated over it (laser).
    :param base: Base array on which we wish to iterate another array.
    :param laser: Secondary array which will be iterated over the base array. Axes have to be of odd lengths in order
                  for it to have a well defined single pixel center.
    :param pad_value: Value of the padded region.
    :returns: Padded version of the base array, along with the number of added rows and columns
    """

    laser_rows, laser_cols = laser.shape
    if laser_rows % 2 == 0 or laser_cols % 2 == 0:
        raise Exception(f"Laser shape has to be odd in order to have a well defined single pixel center")
    rows_pad, cols_pad = laser_rows // 2, laser_cols // 2
    padded_base = numpy.pad(base, ((rows_pad, rows_pad), (cols_pad, cols_pad)), 'constant', constant_values=pad_value)
    return padded_base, rows_pad, cols_pad


def pad_values(laser):
    """
    Returns the minimum necessary rows, cols to pad an array with if we want to iterated over all of it with a laser
    :param laser: Array of the shape of the laser which we want to iterated over a datamap.
    :returns: rows_pad, cols_pad, the number of rows and columns we need to pad the array with.
    """
    rows_pad, cols_pad = laser.shape[0] // 2, laser.shape[1] // 2
    return rows_pad, cols_pad


def array_unpadder(padded_base, laser):
    """
    Function used to unpad a padded array (padded_base) according to the size of the secondary array being iterated over
    it (laser).
    :param padded_base: Padded Base array which we wish to unpad.
    :param laser: Secondary array which has been iterated over padded_base. Axes have to be of odd lengths in order for
                  it to have a well defined single pixel center.
    :returns: An unpadded version of the padded_base.
    """

    laser_rows, laser_cols = laser.shape
    if laser_rows % 2 == 0 or laser_cols % 2 == 0:
        raise Exception(f"Laser shape has to be odd in order to have a well defined single pixel center")
    rows_pad, cols_pad = laser_rows // 2, laser_cols // 2
    # laser_received[int(h_pad / 2):-int(h_pad / 2), int(w_pad / 2):-int(w_pad / 2)]
    unpadded_base = padded_base[rows_pad:-rows_pad, cols_pad:-cols_pad]
    return unpadded_base


def datamap_generator(shape, sources, molecules, random_state=None):
    """
    Function to generate a datamap with randomly located molecules.
    :param shape: A tuple representing the shape of the datamap. If only 1 number is passed, a square datamap will be
                  generated.
    :param sources: Number of molecule sources to be randomly placed on the datamap.
    :param molecules: Average number of molecules contained on each source. The actual number of molecules will be
                      determined by poisson sampling.
    :returns: A datamap containing the randomly placed molecules
    """
    numpy.random.seed(random_state)
    if type(shape) == int:
        shape = (shape, shape)
    datamap = numpy.zeros(shape)
    for i in range(sources):
        row, col = numpy.random.randint(0, shape[0]), numpy.random.randint(0, shape[1])
        datamap[row, col] = numpy.random.poisson(molecules)

    return datamap


def molecules_symmetry(pre_bleach, post_bleach):
    """
    Function to compare the ratio of surviving molecules in the upper vs lower half of a datamap.
    :param pre_bleach: The datamap before bleaching it.
    :param post_bleach: The datamap after bleaching it.
    :returns: Ratio of molecules surviving bleach, split between upper half and lower half
    """
    # We have to compare the same datamap before and after applying lasers on it, so the shape has to be the same
    if pre_bleach.shape != post_bleach.shape:
        raise ValueError("Both pre and post bleach datamaps need to be of the same shape")

    # if there is an odd number of rows, the last row of the upper half will be the first row of the lower half
    if pre_bleach.shape[0] % 2 == 0:
        pre_bleach_uhm = numpy.sum(pre_bleach[0:pre_bleach.shape[0] // 2, :])
        pre_bleach_lhm = numpy.sum(pre_bleach[pre_bleach.shape[0] // 2:, :])
        post_bleach_uhm = numpy.sum(post_bleach[0:post_bleach.shape[0] // 2, :])
        post_bleach_lhm = numpy.sum(post_bleach[post_bleach.shape[0] // 2:, :])
    else:
        pre_bleach_uhm = numpy.sum(pre_bleach[0:pre_bleach.shape[0] // 2 + 1, :])
        pre_bleach_lhm = numpy.sum(pre_bleach[pre_bleach.shape[0] // 2:, :])
        post_bleach_uhm = numpy.sum(post_bleach[0:post_bleach.shape[0] // 2 + 1, :])
        post_bleach_lhm = numpy.sum(post_bleach[post_bleach.shape[0] // 2:, :])

    uh_ratio = post_bleach_uhm / pre_bleach_uhm
    lh_ratio = post_bleach_lhm / pre_bleach_lhm
    return uh_ratio, lh_ratio


def molecules_survival(pre_bleach, post_bleach):
    """
    Returns the ratio of surviving molecules
    :param pre_bleach: The datamap before bleaching it.
    :param post_bleach: The datamap after bleaching it.
    :return: Ratio of molecules surviving bleach
    """
    return numpy.sum(post_bleach) / numpy.sum(pre_bleach)


def float_to_array_verifier(float_or_array, shape):
    """
    This function serves to verify if a certain input is a float or an array. If it is a float, it will return an array
    of shape (shape) filled with the float value. If it is an array, it will verify if it is of the appropriate shape.
    If it is neither, it will return an error
    :param float_or_array: Either a float or an array containing floats
    :param shape: The shape we want for our array (tuple)
    :returns: An array of the appropriate shape
    """
    if type(float_or_array) is float:
        returned_array = numpy.ones(shape) * float_or_array
    elif type(float_or_array) is numpy.ndarray and shape == float_or_array.shape:
        returned_array = numpy.copy(float_or_array)
    else:
        raise TypeError("Has to be either a float or an array of same shape as the ROI")
    return returned_array


def dict_write_func(file, dictio):
    """
    aha
    :param file:
    :param dictio:
    :return:
    """
    f = open(file, 'a')
    f.write(str(dictio))
    f.write("\n")
    f.close()


def event_reader(file):
    """
    Read events from a file containing event dictionaries and return the dicts to a listé
    :param file: Path to the txt file containing the dict for the events
    :return: A list containing the dicts of every identified event in a video
    """
    events_list = []
    f = open(file, 'r')
    lines = f.readlines()
    for line_idx, line in enumerate(lines):
        events_list.append(eval(line.strip()))
    return events_list


def add_event(file, start_frame, end_frame, start_row, end_row, start_col, end_col):
    """
    *** PT QUE JE POURRAIS TRAVAILLER AVEC DES SLICES DANS LE DICT À PLACE? PT PLUS FACILE À MANIP APRÈS IDK ***
    Function that allows a user to easily store an event in a file, which can later be read with the event_reader func.
    :param file: File to write the dict to. The goal is to use 1 text file to which we will write all the vents for
                 1 video.
    :param start_frame: Frame number for the start of the event
    :param start_row: Frame number for the end of the event
    :param start_col: Starting column for the left of the event
    :param end_frame: Ending column for the right of the event
    :param end_row: Starting row for the top of the event
    :param end_col: Ending row for the bottom of the event
    """
    event = {"start frame": start_frame,
             "end frame": end_frame,
             "start col": start_col,
             "end col": end_col,
             "start row": start_row,
             "end row": end_row}
    dict_write_func(file, event)


def get_light_curve(video_path, event):
    """
    aha
    :param video: The path to the video file from which we want to extract an event light curve (str)
    :param event: A dictionary containing the start and end info for frames, rows, columns of an event (dict)
    :return: A vector representing the mean intensity accros the frames of the event
    """
    data_vid = tifffile.imread(video_path)
    event_data = data_vid[event["start frame"]: event["end frame"],
                          event["start row"]: event["end row"],
                          event["start col"]: event["end col"]]
    mean_photons = numpy.mean(event_data, axis=(1, 2))

    return mean_photons


def rescale_data(data, to_int=True, divider=1):
    """
    Function to rescale the data (made for light curves, might be of use elsewhere) between 1 and max-min
    :param data: data to rescale.
    :param to_int: Determines whether the data is truncated to ints after being normalized. Useful for using the
                   fast acquisition function.
    :return: The data rescaled between 1 and max(data) - min(data)
    """
    b, a = numpy.max(data) - numpy.min(data), 1
    normalized = ((b - a)/divider) * ((data - numpy.min(data)) / (numpy.max(data) - numpy.min(data))) + a
    if to_int:
        normalized = normalized.astype(int)
    return normalized


def shift_data(data, peak_idx=5):
    """
    Function to shift the data (made for light curves, might be of use elsewhere) so the peak is on idx 5
    :param data: data to shift
    :param peak_idx: idx at which we want the peak to be
    :return: The shifted data
    """
    peak_arg = numpy.argmax(data)
    if peak_arg >= peak_idx:
        shifted_curve = data[peak_arg - peak_idx:]
        while len(shifted_curve) != 40:
            shifted_curve = numpy.append(shifted_curve, shifted_curve[-1])
    else:
        shifted_curve = numpy.zeros(data.shape)
        shifted_curve[:peak_idx - peak_arg] = data[0]
        shifted_curve[peak_idx - peak_arg: peak_idx] = data[:peak_arg]
        shifted_curve[peak_idx:] = data[peak_arg: - (peak_idx - peak_arg)]
    return shifted_curve


def get_avg_lightcurve(light_curves):
    """
    This function takes as input a list of light curves and processes them so they are rescaled and shifted to align
    their peaks. It then return the avg light curve as well as its standard deviation, so we can sample a light curve
    for event simulation.
    :return:
    """
    shifted_curves = []
    for curve in light_curves:
        rescaled_curve = rescale_data(curve, to_int=False, divider=1)
        shifted_curve = shift_data(rescaled_curve, peak_idx=5)
        shifted_curves.append(shifted_curve)

    avg_shifted_curves = numpy.mean(shifted_curves, axis=0)
    std_shifted_curves = numpy.std(shifted_curves, axis=0)
    return avg_shifted_curves, std_shifted_curves


def savitzky_golay(y, window_size, order, deriv=0, rate=1):
    r"""Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
    The Savitzky-Golay filter removes high frequency noise from data.
    It has the advantage of preserving the original shape and
    features of the signal better than other types of filtering
    approaches, such as moving averages techniques.
    Parameters
    ----------
    y : array_like, shape (N,)
        the values of the time history of the signal.
    window_size : int
        the length of the window. Must be an odd integer number.
    order : int
        the order of the polynomial used in the filtering.
        Must be less then `window_size` - 1.
    deriv: int
        the order of the derivative to compute (default = 0 means only smoothing)
    Returns
    -------
    ys : ndarray, shape (N)
        the smoothed signal (or it's n-th derivative).
    Notes
    -----
    The Savitzky-Golay is a type of low-pass filter, particularly
    suited for smoothing noisy data. The main idea behind this
    approach is to make for each point a least-square fit with a
    polynomial of high order over a odd-sized window centered at
    the point.
    Examples
    --------
    t = np.linspace(-4, 4, 500)
    y = np.exp( -t**2 ) + np.random.normal(0, 0.05, t.shape)
    ysg = savitzky_golay(y, window_size=31, order=4)
    import matplotlib.pyplot as plt
    plt.plot(t, y, label='Noisy signal')
    plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original signal')
    plt.plot(t, ysg, 'r', label='Filtered signal')
    plt.legend()
    plt.show()
    References
    ----------
    .. [1] A. Savitzky, M. J. E. Golay, Smoothing and Differentiation of
       Data by Simplified Least Squares Procedures. Analytical
       Chemistry, 1964, 36 (8), pp 1627-1639.
    .. [2] Numerical Recipes 3rd Edition: The Art of Scientific Computing
       W.H. Press, S.A. Teukolsky, W.T. Vetterling, B.P. Flannery
       Cambridge University Press ISBN-13: 9780521880688
    """

    # try:
    #     window_size = numpy.abs(numpy.int(window_size))
    #     order = numpy.abs(numpy.int(order))
    # except ValueError, msg:
    #     raise ValueError("window_size and order have to be of type int")
    if window_size % 2 != 1 or window_size < 1:
        raise TypeError("window_size size must be a positive odd number")
    if window_size < order + 2:
        raise TypeError("window_size is too small for the polynomials order")
    order_range = range(order+1)
    half_window = (window_size -1) // 2
    # precompute coefficients
    b = numpy.mat([[k**i for i in order_range] for k in range(-half_window, half_window+1)])
    m = numpy.linalg.pinv(b).A[deriv] * rate**deriv * math.factorial(deriv)
    # pad the signal at the extremes with
    # values taken from the signal itself
    firstvals = y[0] - numpy.abs( y[1:half_window+1][::-1] - y[0] )
    lastvals = y[-1] + numpy.abs(y[-half_window-1:-1][::-1] - y[-1])
    y = numpy.concatenate((firstvals, y, lastvals))
    return numpy.convolve( m[::-1], y, mode='valid')


def sample_light_curve(light_curves):
    """
    This function allows to sample from a distribution of light curves and handles the smoothing and correcting values.
    :param light_curves: list containing the light curves we wish to do stats and sample from
    :return: A smoothed curve sampled from the distribution
    """
    avg_curve, std_curve = get_avg_lightcurve(light_curves)
    sampled_curve = numpy.random.normal(avg_curve, std_curve)
    sampled_curve = numpy.where(sampled_curve >= 1, sampled_curve, 1)
    smoothed_sampled = savitzky_golay(sampled_curve, 5, 2)   # These params give nice curves :)
    return smoothed_sampled


def flash_generator(events_path, video_path):
    """
    C'EST BAD COMME NOM
    The goal of this function is to generate the light curves (?) needed to generate flashes.
    Basically this just wraps up the work of the previous light curve functions for ease of use
    when designing an experiment or something
    :return:
    """
    events = event_reader(events_path)

    curves = []
    for event in events:
        light_curve = get_light_curve(video_path, event)
        curves.append(light_curve)

    sampled_light_curve = sample_light_curve(curves)

    return sampled_light_curve


def generate_fiber_with_synapses(datamap_shape, fibre_min, fibre_max, n_synapses, min_dist, polygon_scale=(5, 10)):
    """
    This func allows a user to generate a fiber object and synapses attached to it.
    :param datamap_shape: shape of the image to which we will add the fiber and synapses
    :param fibre_min: min position for the fibre to start at
    :param fibre_max: max position for the fibre to start at
    :param n_synapses: number of synapses to put on the fiber
    :param min_dist: min distance we want to have between the synapses. this is to make sure we don't have overlapping
                     synapses
    :param polygon_scale: values from which the polygon size will be sampled
    :return:
    """
    min_array, max_array = numpy.asarray((fibre_min, fibre_min)), numpy.asarray((fibre_max, fibre_max))
    # jpense jpeux controller l'angle aussi
    fibre = temporal.Fiber(random_params={"num_points": (fibre_min, fibre_max),
                                                    "pos": [numpy.zeros((1, 2)) + min_array,
                                                            datamap_shape - max_array],
                                                    "scale": (1, 5)})
    n_added = 0
    synapse_positions = numpy.empty((0, 2))
    while n_added != n_synapses:
        sampled_node = numpy.asarray(random.sample(list(fibre.nodes_position), 1)[0].astype(int))
        if numpy.less_equal(sampled_node, 0).any() or \
                numpy.greater_equal(sampled_node, datamap_shape - numpy.ones((1, 1))).any():
            continue
        if n_added == 0:
            synapse_positions = numpy.append(synapse_positions, sampled_node)
            synapse_positions = numpy.expand_dims(synapse_positions, 0).astype(int)
            n_added += 1
            continue
        # comparer la distance du point samplé à tous les points dans la liste
        # vérifier qu'elle est plus grande que min_distance pour tous les points déjà présents,
        # si c'est le cas, l'ajouter à la liste, sinon continuer le while :)
        else:
            sample_to_verify = numpy.expand_dims(numpy.copy(sampled_node), axis=0).astype(int)
            synapse_positions = numpy.append(synapse_positions, sample_to_verify, axis=0).astype(int)
            distances = cdist(synapse_positions, synapse_positions)
            distances[n_added, n_added] = min_dist + 1
            if numpy.less_equal(distances[n_added, :], min_dist).any():
                # at least 1 elt is closer than 10 pixels to an already present elt so remove it :)
                synapse_positions = numpy.delete(synapse_positions, n_added, axis=0)
            else:
                # good to add to the list
                n_added += 1

    polygon_list = []
    for node in synapse_positions:
        polygon = temporal.Polygon(random_params={"pos": [node, node],
                                                  "scale": polygon_scale})
        polygon_list.append(polygon)

    return fibre, polygon_list


def generate_secondary_fibers(datamap_shape, main_fiber, n_sec, min_dist=10, sec_len=(2, 6)):
    """
    Similar to the synapse function, but with fibers instead. The goal would be to pass
    an already existing fiber to this func and simply spawn the secondary fibers
    :return:
    """
    n_added = 0
    sec_fiber_positions = numpy.empty((0, 2))
    angle_at_position = []
    n_secondary = int(random.uniform(*n_sec))
    n_loops = 0
    while n_added != n_secondary:
        n_loops += 1
        if n_loops >= 100 * n_secondary:
            break
        # sampled_node = numpy.asarray(random.sample(list(main_fiber.nodes_position), 1)[0].astype(int))
        sample_idx = numpy.random.randint(len(main_fiber.nodes_position))
        sampled_node = main_fiber.nodes_position[sample_idx, :].astype(int)
        if numpy.less_equal(sampled_node, 0).any() or \
                numpy.greater_equal(sampled_node, datamap_shape - numpy.ones((1, 1))).any():
            continue
        if n_added == 0:
            sec_fiber_positions = numpy.append(sec_fiber_positions, sampled_node)
            sec_fiber_positions = numpy.expand_dims(sec_fiber_positions, 0).astype(int)
            angle_at_position.append(main_fiber.angles[sample_idx])
            n_added += 1
            continue
        else:
            sample_to_verify = numpy.expand_dims(numpy.copy(sampled_node), axis=0).astype(int)
            sec_fiber_positions = numpy.append(sec_fiber_positions, sample_to_verify, axis=0).astype(int)
            distances = cdist(sec_fiber_positions, sec_fiber_positions)
            distances[n_added, n_added] = min_dist + 1
            if numpy.less_equal(distances[n_added, :], min_dist).any():
                # at least 1 elt is closer than 10 pixels to an already present elt so remove it :)
                sec_fiber_positions = numpy.delete(sec_fiber_positions, n_added, axis=0)
            else:
                # good to add to the list
                angle_at_position.append(main_fiber.angles[sample_idx])
                n_added += 1

    sec_fibers_list = []
    for node in sec_fiber_positions:
        sec_fiber = temporal.Fiber(random_params={"num_points": sec_len,
                                                  "pos": [node, node],
                                                  "scale": (1, 3),
                                                  "angle": (- 0.25, 0.25)})
        sec_fibers_list.append(sec_fiber)

    return sec_fibers_list


def generate_synapses_on_fiber(datamap_shape, main_fiber, n_syn, min_dist, synapse_scale=(5, 10)):
    """
    Instead of generating a fiber with synapses on it, I will simply generate synapses on a fiber
    :return:
    """
    n_added = 0
    synapse_positions = numpy.empty((0, 2))
    n_synapses = int(random.uniform(*n_syn))
    n_loops = 0
    while n_added != n_synapses:
        n_loops += 1
        if n_loops >= 100 * n_synapses:
            break
        sampled_node = numpy.asarray(random.sample(list(main_fiber.nodes_position), 1)[0].astype(int))
        if numpy.less_equal(sampled_node, 0).any() or \
                numpy.greater_equal(sampled_node, datamap_shape - numpy.ones((1, 1))).any():
            continue
        if n_added == 0:
            synapse_positions = numpy.append(synapse_positions, sampled_node)
            synapse_positions = numpy.expand_dims(synapse_positions, 0).astype(int)
            n_added += 1
            continue
        # comparer la distance du point samplé à tous les points dans la liste
        # vérifier qu'elle est plus grande que min_distance pour tous les points déjà présents,
        # si c'est le cas, l'ajouter à la liste, sinon continuer le while :)
        else:
            sample_to_verify = numpy.expand_dims(numpy.copy(sampled_node), axis=0).astype(int)
            synapse_positions = numpy.append(synapse_positions, sample_to_verify, axis=0).astype(int)
            distances = cdist(synapse_positions, synapse_positions)
            distances[n_added, n_added] = min_dist + 1
            if numpy.less_equal(distances[n_added, :], min_dist).any():
                # at least 1 elt is closer than 10 pixels to an already present elt so remove it :)
                synapse_positions = numpy.delete(synapse_positions, n_added, axis=0)
            else:
                # good to add to the list
                n_added += 1

    synapse_list = []
    for node in synapse_positions:
        polygon = temporal.Polygon(random_params={"pos": [node, node],
                                                  "scale": synapse_scale})
        synapse_list.append(polygon)

    return synapse_list


def generate_synaptic_fibers(image_shape, main_nodes, n_sec_fibers, n_synapses, min_fiber_dist=3, min_synapse_dist=1,
                             sec_fiber_len=(10, 20), synapse_scale=(5, 5)):
    """
    This function wraps up the generation of fibers with secondary branches and synapses in a neat little package :)
    - Add variable number of synapses, distances, ?
    - Add "position identifiers" to the synapses so I can easily make them flash after
    - ??
    :return:
    """

    # generate an empty image
    image = numpy.zeros(image_shape)

    # generate the main fiber
    min_nodes, max_nodes = main_nodes[0], main_nodes[1]
    min_array, max_array = numpy.asarray((min_nodes, min_nodes)), numpy.asarray((max_nodes, max_nodes))
    fibre_rand = temporal.Fiber(random_params={"num_points": (min_nodes, max_nodes),
                                               "pos": [numpy.zeros((1, 2)) + min_array,
                                                       image.shape - max_array],
                                               "scale": (1, 5)})

    # generate secondary fibers
    # ces params là devraient être ajustables
    sec_fibers = generate_secondary_fibers(image_shape, fibre_rand, n_sec_fibers, min_fiber_dist, sec_len=sec_fiber_len)

    # generate synapses attached to the secondary fibers
    synapses_lists = []
    for secondary_fiber in sec_fibers:
        ith_fiber_synapses = generate_synapses_on_fiber(image_shape, secondary_fiber, n_synapses, min_synapse_dist,
                                                        synapse_scale=synapse_scale)
        synapses_lists.append(ith_fiber_synapses)

    roi = ((0, 0), image_shape)  # jtrouve que la façon de gérer la shape de l'ensemble est weird
    ensemble_test = temporal.Ensemble(roi=roi)
    ensemble_test.append(fibre_rand)
    for idx, sec_fiber in enumerate(sec_fibers):
        ensemble_test.append(sec_fiber)
        for synapse in synapses_lists[idx]:
            ensemble_test.append(synapse)

    # frame = ensemble_test.return_frame()

    return ensemble_test, synapses_lists


def generate_raster_pixel_list(n_pixels_to_add, starting_pixel, img):
    """
    The goal is to generate a raster scan pixel list from starting_pixel, containing a maximum of n_pixels_to_add
    pixels and a minimum of img.shape[0] * img.shape[1] pixels.
    :param n_pixels_to_add:
    :param starting_pixel:
    :param img:
    :return:
    """
    # makes sure we don't pass twice over the same pixel, might be removed later
    # n_pixels_img = img.shape[0] * img.shape[1]
    # if n_pixels_to_add <= n_pixels_img:
    #     n_iters = n_pixels_to_add
    # else:
    #     n_iters = n_pixels_img

    return_list = []
    current_idx = starting_pixel
    for i in range(n_pixels_to_add):
        return_list.append(tuple(current_idx))
        current_idx[1] += 1
        if current_idx[1] >= img.shape[1]:
            current_idx[1] = 0
            current_idx[0] += 1
        if current_idx[0] >= img.shape[0]:
            current_idx[0] = 0

    return return_list