from hls_sync import __version__

from setuptools import setup, find_packages
setup(
    name = "HLS Sync",
    version = __version__,
    packages = find_packages(),
    entry_points = {
        'console_scripts': [ 'hls-sync = hls_sync.sync:main' ]
        },

    author = "Mingcai SHEN",
    author_email = "archsh@gmail.com",
    description = "HTTP Live Streaming Fetcher",
    license = "GNU GPL",
    keywords = "video streaming live",
)