import "package:flutter/material.dart";

class OrdersScreen extends StatelessWidget {
  const OrdersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: const [
        Text("Orders", style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
        SizedBox(height: 12),
        Text(
          "The mobile scaffold reserves this tab for buyer mock checkout and seller fulfillment updates. "
          "REST and MCP expose the same order states: address_pending, payment_pending, paid, confirmed, shipped, delivered, cancelled.",
          style: TextStyle(height: 1.5),
        ),
      ],
    );
  }
}
