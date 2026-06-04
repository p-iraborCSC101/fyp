import math

from geometry_msgs.msg import PoseArray
from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String
import rclpy


class HumanObstaclesNode(Node):
    def __init__(self) -> None:
        super().__init__("human_obstacles")
        qos = QoSProfile(depth=10)

        self._frame_id = str(self.declare_parameter("frame_id", "world").value)
        self._actor_prefix = str(self.declare_parameter("actor_prefix", "human_").value)
        self._radius = float(self.declare_parameter("obstacle_radius", 0.35).value)
        self._min_speed = float(self.declare_parameter("min_speed", 0.05).value)
        self._min_z = float(self.declare_parameter("min_z", 0.9).value)
        self._actor_topic = str(
            self.declare_parameter("actor_pose_topic", "/actor_poses").value
        )
        self._status_pub = self.create_publisher(String, "/human_obstacles_status", qos)
        self._pose_pub = self.create_publisher(PoseArray, "/dynamic_obstacles", qos)

        self._poses_sub = self.create_subscription(
            PoseArray,
            self._actor_topic,
            self._on_poses,
            qos,
        )

        self.get_logger().info("Human obstacles node started.")

    def _on_poses(self, msg: PoseArray) -> None:
        if not msg.poses:
            return

        filtered = PoseArray()
        filtered.header = msg.header
        filtered.header.frame_id = self._frame_id

        for pose in msg.poses:
            # Basic filter to avoid NaNs and noisy zeros.
            if not (math.isfinite(pose.position.x) and math.isfinite(pose.position.y)):
                continue
            if math.isfinite(pose.position.z) and pose.position.z < self._min_z:
                continue
            filtered.poses.append(pose)

        if not filtered.poses:
            return

        self._pose_pub.publish(filtered)
        self._status_pub.publish(
            String(data=f"dynamic_obstacles={len(filtered.poses)} radius={self._radius}")
        )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HumanObstaclesNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
