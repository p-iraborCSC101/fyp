from setuptools import setup

package_name = 'emergency_sensing'

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
    description='Simulated emergency alert publisher for the FYP ROS 2 workspace.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'emergency_publisher = emergency_sensing.emergency_publisher:main',
            'sensor_simulator = emergency_sensing.sensor_simulator:main',
            'alert_fusion = emergency_sensing.alert_fusion:main',
            'sensor_dashboard = emergency_sensing.sensor_dashboard:main',
        ],
    },
)
