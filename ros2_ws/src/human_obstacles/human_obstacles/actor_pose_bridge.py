from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription(
        [
            Node(
                package="ros_gz_bridge",
                executable="parameter_bridge",
                name="actor_pose_bridge",
                arguments=[
                    "/actor_poses@geometry_msgs/msg/PoseArray[gz.msgs.Pose_V",
                ],
                output="screen",
            ),
        ]
    )
