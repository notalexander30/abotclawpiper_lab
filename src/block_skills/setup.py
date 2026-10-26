from glob import glob
from setuptools import setup

setup(
    name='block_skills', version='0.1.0', packages=['block_skills'],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/block_skills']),
        ('share/block_skills', ['package.xml']),
        ('share/block_skills/launch', glob('launch/*.launch.py')),
        ('share/block_skills/config', glob('config/*')),
    ],
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Project maintainers', maintainer_email='maintainer@example.com',
    description='Gazebo state based UR10e block skills', license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={'console_scripts': [
        'server = block_skills.server:main',
        'blocks = block_skills.cli:main',
        'check = block_skills.check:main',
    ]},
)
