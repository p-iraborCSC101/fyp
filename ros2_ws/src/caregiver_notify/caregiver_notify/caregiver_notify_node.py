import json
import time

from rclpy.node import Node
from rclpy.qos import QoSProfile
from std_msgs.msg import String
import rclpy


class CaregiverNotifyNode(Node):
    def __init__(self) -> None:
        super().__init__("caregiver_notify")
        qos = QoSProfile(depth=10)

        self._last_alert_ts = 0.0
        self._cooldown_s = float(self.declare_parameter("cooldown_s", 10.0).value)
        self._caregiver_id = str(self.declare_parameter("caregiver_id", "ward-a").value)

        self._alert_sub = self.create_subscription(
            String,
            "/emergency_alert",
            self._on_alert,
            qos,
        )
        self._status_sub = self.create_subscription(
            String,
            "/robot_status",
            self._on_status,
            qos,
        )
        self._notify_pub = self.create_publisher(String, "/caregiver_notify", qos)
        self._status_pub = self.create_publisher(String, "/caregiver_status", qos)

        self.get_logger().info("Caregiver notification node started.")

    def _on_alert(self, msg: String) -> None:
        now = time.time()
        if now - self._last_alert_ts < self._cooldown_s:
            return

        payload = {
            "caregiver_id": self._caregiver_id,
            "type": "alert",
            "timestamp": now,
            "message": msg.data,
        }
        self._notify_pub.publish(String(data=json.dumps(payload)))
        self._last_alert_ts = now

    def _on_status(self, msg: String) -> None:
        payload = {
            "caregiver_id": self._caregiver_id,
            "type": "robot_status",
            "timestamp": time.time(),
            "message": msg.data,
        }
        self._status_pub.publish(String(data=json.dumps(payload)))


def main(args=None) -> None:
    rclpy.init(args=args)
    node = CaregiverNotifyNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
