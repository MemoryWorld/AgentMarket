import "package:file_picker/file_picker.dart";
import "package:flutter/material.dart";

import "../services/api_client.dart";

class SellScreen extends StatefulWidget {
  const SellScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<SellScreen> createState() => _SellScreenState();
}

class _SellScreenState extends State<SellScreen> {
  final emailController = TextEditingController(text: "seller@example.com");
  final displayNameController = TextEditingController(text: "Seller Agent");
  final codeController = TextEditingController();
  final titleController = TextEditingController(text: "Used mirrorless camera");
  final descriptionController = TextEditingController(text: "Compact body, charger included.");
  final cityController = TextEditingController(text: "sydney-au");
  final priceController = TextEditingController(text: "25900");

  String debugCode = "";
  String token = "";
  String status = "Authenticate, then create a manual or AI-assisted draft.";
  String? draftId;

  @override
  void dispose() {
    emailController.dispose();
    displayNameController.dispose();
    codeController.dispose();
    titleController.dispose();
    descriptionController.dispose();
    cityController.dispose();
    priceController.dispose();
    super.dispose();
  }

  Future<void> requestOtp() async {
    final code = await widget.apiClient.requestOtp(emailController.text);
    setState(() {
      debugCode = code;
      status = "OTP requested. Debug code displayed below for local development.";
    });
  }

  Future<void> verifyOtp() async {
    final accessToken = await widget.apiClient.verifyOtp(
      email: emailController.text,
      code: codeController.text,
      displayName: displayNameController.text,
      citySlug: cityController.text,
    );
    setState(() {
      token = accessToken;
      status = "Authenticated. Seller token ready for write actions.";
    });
  }

  Future<void> createDraft() async {
    final payload = await widget.apiClient.createDraft(
      token: token,
      title: titleController.text,
      description: descriptionController.text,
      citySlug: cityController.text,
      askingPriceCents: int.tryParse(priceController.text) ?? 0,
    );
    setState(() {
      draftId = payload["id"] as String?;
      status = "Manual draft created.";
    });
  }

  Future<void> runAutofill() async {
    final result = await FilePicker.platform.pickFiles(allowMultiple: true, type: FileType.image);
    if (result == null || result.files.isEmpty) return;
    final payload = await widget.apiClient.runAutofill(
      token: token,
      citySlug: cityController.text,
      files: result.files,
    );
    setState(() {
      draftId = payload["id"] as String?;
      titleController.text = (payload["title"] as String?) ?? titleController.text;
      descriptionController.text = (payload["description"] as String?) ?? descriptionController.text;
      status = "AI autofill completed from selected photos.";
    });
  }

  Future<void> generateImage() async {
    if (draftId == null) return;
    await widget.apiClient.generateSaleImage(token: token, draftId: draftId!);
    setState(() {
      status = "AI sale image generated for the active draft.";
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        const Text("Sell with AI", style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Text(status, style: const TextStyle(height: 1.45)),
        const SizedBox(height: 20),
        TextField(controller: emailController, decoration: const InputDecoration(labelText: "Seller email")),
        TextField(controller: displayNameController, decoration: const InputDecoration(labelText: "Display name")),
        TextField(controller: cityController, decoration: const InputDecoration(labelText: "City slug")),
        const SizedBox(height: 12),
        FilledButton(onPressed: requestOtp, child: const Text("Request debug OTP")),
        if (debugCode.isNotEmpty) Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text("Debug OTP: $debugCode"),
        ),
        const SizedBox(height: 16),
        TextField(controller: codeController, decoration: const InputDecoration(labelText: "OTP code")),
        FilledButton(onPressed: verifyOtp, child: const Text("Verify")),
        const Divider(height: 32),
        TextField(controller: titleController, decoration: const InputDecoration(labelText: "Listing title")),
        TextField(controller: descriptionController, decoration: const InputDecoration(labelText: "Description")),
        TextField(controller: priceController, decoration: const InputDecoration(labelText: "Price in cents")),
        const SizedBox(height: 12),
        FilledButton(onPressed: token.isEmpty ? null : createDraft, child: const Text("Create manual draft")),
        OutlinedButton(onPressed: token.isEmpty ? null : runAutofill, child: const Text("Auto-fill from photos")),
        OutlinedButton(onPressed: draftId == null ? null : generateImage, child: const Text("Generate sale image")),
      ],
    );
  }
}
