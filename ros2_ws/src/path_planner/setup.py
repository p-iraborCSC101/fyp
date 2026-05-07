from setuptools import setup

package_name = 'path_planner'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', [f'resource/{package_name}']),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Paula Irabor',
    maintainer_email='paula.irabor@example.com',
    description='Grid-based A* planner node for emergency response routes.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'path_planner = path_planner.path_planner_node:main',
        ],
    },
)
