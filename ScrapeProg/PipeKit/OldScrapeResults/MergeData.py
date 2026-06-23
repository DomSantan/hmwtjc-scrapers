import pandas as pd

# Load both datasets
main = pd.read_csv("PipekitProducts.csv")
extra = pd.read_csv("PipekitProductsVariants.csv")

# Perform a left join on BOTH `offer_url` and `sku`
merged = pd.merge(
    main,
    extra,
    left_on=["offer_url", "sku"],
    right_on=["offer_url", "sku_from_meta"],  # Use actual key from extra
    how="left"
)

# Drop duplicate rows (fully identical)
merged = merged.drop_duplicates()

# Optional: drop `sku_from_meta` if you don’t need it anymore
merged = merged.drop(columns=["sku_from_meta"], errors='ignore')

# Save final result
merged.to_csv("Final_Pipekit_Products.csv", index=False)
print("✅ Final CSV saved: Final_Pipekit_Products.csv")
