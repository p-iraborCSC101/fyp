from geometry_msgs.msg import PoseArray
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import QoSProfile
import rclpy


class ActorPoseExtractorNode(Node):
    def __init__(self) -> None:
        super().__init__("actor_pose_extractor")
        qos = QoSProfile(depth=10)

        self._frame_id = str(self.declare_parameter("frame_id", "world").value)
        self._actor_prefix = str(self.declare_parameter("actor_prefix", "human_").value)

        self._pose_pub = self.create_publisher(PoseArray, "/human_actor_poses", qos)
        self._pose_sub = self.create_subscription(
            PoseArray,
            "/actor_poses",
            self._on_actor_poses,
            qos,
        )

        self.get_logger().info("Actor pose extractor started.")

    def _on_actor_poses(self, msg: PoseArray) -> None:
        if not msg.poses:
            return

        filtered = PoseArray()
        filtered.header = msg.header
        filtered.header.frame_id = self._frame_id
        filtered.poses = list(msg.poses)

        self._pose_pub.publish(filtered)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ActorPoseExtractorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
