import "dart:convert";

import "package:file_picker/file_picker.dart";
import "package:http/http.dart" as http;

import "../models/listing.dart";

class ApiClient {
  ApiClient({this.baseUrl = "http://10.0.2.2:8000/api/v1"});

  final String baseUrl;

  Future<List<ListingSummary>> fetchListings() async {
    final response = await http.get(Uri.parse("$baseUrl/listings"));
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    final items = payload["items"] as List<dynamic>? ?? [];
    return items
        .map((item) => ListingSummary.fromJson(item as Map<String, dynamic>))
        .toList();
  }

  Future<String> requestOtp(String email) async {
    final response = await http.post(
      Uri.parse("$baseUrl/auth/email/request-code"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({"email": email}),
    );
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return (payload["debug_code"] as String?) ?? "";
  }

  Future<String> verifyOtp({
    required String email,
    required String code,
    required String displayName,
    required String citySlug,
  }) async {
    final response = await http.post(
      Uri.parse("$baseUrl/auth/email/verify"),
      headers: {"Content-Type": "application/json"},
      body: jsonEncode({
        "email": email,
        "code": code,
        "display_name": displayName,
        "city_slug": citySlug,
        "country_code": "AU",
      }),
    );
    final payload = jsonDecode(response.body) as Map<String, dynamic>;
    return payload["access_token"] as String;
  }

  Future<Map<String, dynamic>> createDraft({
    required String token,
    required String title,
    required String description,
    required String citySlug,
    required int askingPriceCents,
  }) async {
    final response = await http.post(
      Uri.parse("$baseUrl/draft-listings"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        "title": title,
        "description": description,
        "category_slug": "electronics",
        "asking_price_cents": askingPriceCents,
        "currency_code": "USD",
        "city_slug": citySlug,
      }),
    );
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> runAutofill({
    required String token,
    required String citySlug,
    required List<PlatformFile> files,
  }) async {
    final request = http.MultipartRequest("POST", Uri.parse("$baseUrl/draft-listings/ai-autofill"));
    request.headers["Authorization"] = "Bearer $token";
    request.fields["city_slug"] = citySlug;
    request.fields["currency_code"] = "USD";
    for (final file in files) {
      if (file.path == null) continue;
      request.files.add(await http.MultipartFile.fromPath("files", file.path!));
    }
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> generateSaleImage({
    required String token,
    required String draftId,
  }) async {
    final response = await http.post(
      Uri.parse("$baseUrl/draft-listings/ai-image"),
      headers: {
        "Authorization": "Bearer $token",
        "Content-Type": "application/json",
      },
      body: jsonEncode({
        "draft_id": draftId,
        "style_preset": "clean studio",
        "quality": "medium",
        "size": "1024x1024",
        "background": "auto",
      }),
    );
    return jsonDecode(response.body) as Map<String, dynamic>;
  }
}
