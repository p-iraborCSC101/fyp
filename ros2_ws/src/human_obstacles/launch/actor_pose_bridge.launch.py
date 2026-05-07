from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:
    config = PathJoinSubstitution(
        [FindPackageShare("human_obstacles"), "actor_pose_bridge_config.yaml"]
    )

    return LaunchDescription(
        [
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="actor_pose_bridge",
                parameters=[{"config_file": config}],
                output="screen",
            ),
        ]
    )
