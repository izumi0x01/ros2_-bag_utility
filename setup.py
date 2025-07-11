from setuptools import setup, find_packages
from Cython.Build import cythonize
from setuptools.extension import Extension
import numpy

extensions = [
    Extension("bag_converter", ["src/bag_converter.pyx"]),
    Extension("message_converter", ["src/message_converter.pyx"]),
]

setup(
    name="rosbag2_tools",
    ext_modules=cythonize(extensions, language_level=3),
    package_dir={"": "src"},
)