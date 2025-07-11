# setup.py
from setuptools import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import numpy


extensions = [
    Extension("package.bag_converter", ["package/bag_converter.pyx"]),
    Extension("package.message_converter", ["package/message_converter.pyx"]),
]

setup(
    name="rosbag2_tools",
    ext_modules=cythonize(extensions, language_level=3),
    packages=["package"],
)