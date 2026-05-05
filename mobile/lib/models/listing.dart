class ListingSummary {
  const ListingSummary({
    required this.id,
    required this.slug,
    required this.title,
    required this.askingPriceCents,
    required this.currencyCode,
    required this.citySlug,
    this.primaryImageUrl,
  });

  final String id;
  final String slug;
  final String title;
  final int askingPriceCents;
  final String currencyCode;
  final String citySlug;
  final String? primaryImageUrl;

  factory ListingSummary.fromJson(Map<String, dynamic> json) {
    return ListingSummary(
      id: json["id"] as String,
      slug: json["slug"] as String,
      title: json["title"] as String,
      askingPriceCents: json["asking_price_cents"] as int,
      currencyCode: json["currency_code"] as String,
      citySlug: json["city_slug"] as String,
      primaryImageUrl: json["primary_image_url"] as String?,
    );
  }
}
