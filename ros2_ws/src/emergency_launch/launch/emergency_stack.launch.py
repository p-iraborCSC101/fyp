from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    planner_mode = LaunchConfiguration('planner_mode')

    return LaunchDescription([
        DeclareLaunchArgument(
            'planner_mode',
            default_value='a_star',
            description='Planner mode to use: a_star or rrt_star',
        ),
        Node(
            package='emergency_sensing',
            executable='emergency_publisher',
            name='emergency_publisher',
            output='screen',
        ),
        Node(
            package='path_planner',
            executable='path_planner',
            name='path_planner',
            output='screen',
            parameters=[{'planner_mode': planner_mode}],
        ),
        Node(
            package='response_logger',
            executable='response_logger',
            name='response_logger',
            output='screen',
        ),
    ])
