from hlsfethcer import __version__

from setuptools import setup, find_packages
setup(
    name = "HLS Fetcher",
    version = __version__,
    packages = find_packages(),
    entry_points = {
        'console_scripts': [ 'hls-fetcher = hlsfetcher.player:main' ]
        },

    author = "Mingcai SHEN",
    author_email = "archsh@gmail.com",
    description = "HTTP Live Streaming Fetcher",
    license = "GNU GPL",
    keywords = "video streaming live",
)