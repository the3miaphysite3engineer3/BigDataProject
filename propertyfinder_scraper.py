"""
PropertyFinder Egypt Selenium Scraper
=====================================
Extracts listing data from the embedded __NEXT_DATA__ JSON (Next.js hydration payload)
and JSON-LD schema scripts, which are always present in the page source regardless
of whether React components have finished rendering.

Also generates a comprehensive, self-contained HTML dashboard report.
"""

import json
import time
import re
import sys
import os
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class PropertyFinderScraper:
    BASE_URL = "https://www.propertyfinder.eg/en"

    def __init__(self, headless=True):
        options = Options()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # Try local chromedriver first, fall back to webdriver-manager
        try:
            self.driver = webdriver.Chrome(options=options)
        except Exception:
            from webdriver_manager.chrome import ChromeDriverManager
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options,
            )

        self.wait = WebDriverWait(self.driver, 15)

    # ------------------------------------------------------------------
    # Core extraction: pull __NEXT_DATA__ JSON from any PF page
    # ------------------------------------------------------------------
    def _get_next_data(self):
        """Extract the __NEXT_DATA__ JSON payload embedded by Next.js."""
        try:
            script = self.driver.find_element(By.ID, "__NEXT_DATA__")
            return json.loads(script.get_attribute("textContent"))
        except Exception as e:
            print(f"  ⚠ Could not find __NEXT_DATA__: {e}")
            return None

    def _get_jsonld_schemas(self):
        """Extract all JSON-LD <script> blocks from the page."""
        scripts = self.driver.find_elements(
            By.CSS_SELECTOR, 'script[type="application/ld+json"]'
        )
        schemas = []
        for s in scripts:
            try:
                schemas.append(json.loads(s.get_attribute("textContent")))
            except json.JSONDecodeError:
                pass
        return schemas

    # ------------------------------------------------------------------
    # Listings  (rent / buy search pages)
    # ------------------------------------------------------------------
    def scrape_listings(self, pages=3):
        """Scrape apartment-for-rent listings across multiple pages."""
        all_listings = []

        for page_num in range(1, pages + 1):
            url = (
                f"{self.BASE_URL}/rent/cairo/apartments-for-rent.html"
                f"?page={page_num}"
            )
            print(f"📄 Fetching listings page {page_num}: {url}")
            self.driver.get(url)
            time.sleep(3)  # allow page to settle

            next_data = self._get_next_data()
            if not next_data:
                print("  ⚠ No __NEXT_DATA__ found – skipping page")
                continue

            try:
                raw_listings = (
                    next_data["props"]["pageProps"]["searchResult"]["listings"]
                )
            except (KeyError, TypeError):
                print("  ⚠ Unexpected __NEXT_DATA__ structure – skipping page")
                continue

            for item in raw_listings:
                prop = item.get("property") or item.get("project") or {}
                if not prop:
                    continue

                price_info = prop.get("price", {})
                location = prop.get("location", {})
                specs = prop.get("specifications", {})

                listing = {
                    "listing_id": prop.get("id"),
                    "title": prop.get("title", ""),
                    "property_type": prop.get("property_type", ""),
                    "price": price_info.get("value"),
                    "currency": price_info.get("currency", "EGP"),
                    "price_period": price_info.get("period", ""),
                    "bedrooms": prop.get("bedroom_value")
                        or specs.get("bedroom", {}).get("value"),
                    "bathrooms": prop.get("bathroom_value")
                        or specs.get("bathroom", {}).get("value"),
                    "size_sqm": prop.get("area_value")
                        or specs.get("area", {}).get("value"),
                    "location_full": location.get("full_name", ""),
                    "location_name": location.get("name", ""),
                    "location_path": location.get("path_name", ""),
                    "latitude": (location.get("coordinates") or {}).get("lat"),
                    "longitude": (location.get("coordinates") or {}).get("lon"),
                    "image_url": (prop.get("images", [{}])[0].get("medium")
                                 if prop.get("images") else None),
                    "url": prop.get("links", {}).get("detail", ""),
                }
                all_listings.append(listing)

            print(f"  ✓ Got {len(raw_listings)} listings from page {page_num}")

        print(f"\n✅ Total listings scraped: {len(all_listings)}")
        return all_listings

    # ------------------------------------------------------------------
    # Agencies  (find-broker page)
    # ------------------------------------------------------------------
    def scrape_agencies(self):
        """Scrape agency/broker data from __NEXT_DATA__."""
        url = f"{self.BASE_URL}/find-broker"
        print(f"📄 Fetching agencies: {url}")
        self.driver.get(url)
        time.sleep(3)

        next_data = self._get_next_data()
        if not next_data:
            print("  ⚠ No __NEXT_DATA__ found")
            return []

        agencies = []
        try:
            brokers_raw = (
                next_data["props"]["pageProps"].get("brokers")
                or next_data["props"]["pageProps"].get("agencies")
                or {}
            )
            # brokers is {"data": [...], "meta": {...}} — extract the list
            if isinstance(brokers_raw, dict):
                brokers = brokers_raw.get("data", [])
            elif isinstance(brokers_raw, list):
                brokers = brokers_raw
            else:
                brokers = []

            # Fallback: walk pageProps looking for an array of agency-like dicts
            if not brokers:
                for key, val in next_data["props"]["pageProps"].items():
                    if isinstance(val, dict) and "data" in val:
                        candidate = val["data"]
                        if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict) and "name" in candidate[0]:
                            brokers = candidate
                            break
                    elif isinstance(val, list) and val and isinstance(val[0], dict) and "name" in val[0]:
                        brokers = val
                        break
        except (KeyError, TypeError):
            pass

        for b in brokers:
            if not isinstance(b, dict):
                continue
            logo = b.get("logo", {})
            logo_url = None
            if isinstance(logo, dict):
                links = logo.get("links", {})
                logo_url = links.get("desktop") or links.get("desktopJpg") or logo.get("url")
            elif isinstance(logo, str):
                logo_url = logo
            agencies.append({
                "agency_id": b.get("id") or b.get("clientId"),
                "name": b.get("name", ""),
                "slug": b.get("urlSlug") or b.get("slug", ""),
                "agent_count": b.get("totalAgents") or b.get("agents_count") or b.get("agent_count"),
                "total_properties": b.get("totalProperties"),
                "listings_for_sale": b.get("propertiesResidentialForSaleCount")
                    or b.get("for_sale_count"),
                "listings_for_rent": b.get("propertiesResidentialForRentCount")
                    or b.get("for_rent_count"),
                "commercial_for_sale": b.get("propertiesCommercialForSaleCount"),
                "commercial_for_rent": b.get("propertiesCommercialForRentCount"),
                "phone": b.get("phone", ""),
                "email": b.get("email", ""),
                "address": b.get("address", ""),
                "license_number": b.get("licenseNumber", ""),
                "logo_url": logo_url,
            })

        print(f"  ✓ Scraped {len(agencies)} agencies")
        return agencies

    # ------------------------------------------------------------------
    # New Projects
    # ------------------------------------------------------------------
    def scrape_projects(self):
        """Scrape new/off-plan projects from __NEXT_DATA__."""
        url = f"{self.BASE_URL}/new-projects"
        print(f"📄 Fetching new projects: {url}")
        self.driver.get(url)
        time.sleep(3)

        next_data = self._get_next_data()
        if not next_data:
            print("  ⚠ No __NEXT_DATA__ found")
            return []

        projects = []
        page_props = next_data.get("props", {}).get("pageProps", {})

        # Primary path: searchResult.data.projects (confirmed structure)
        raw_projects = []
        search_result = page_props.get("searchResult", {})
        if isinstance(search_result, dict):
            sr_data = search_result.get("data", {})
            if isinstance(sr_data, dict):
                raw_projects = sr_data.get("projects", [])
                if raw_projects:
                    print(f"  → Found {len(raw_projects)} projects under searchResult.data.projects")

        # Fallback: try top-level keys
        if not raw_projects:
            raw_projects = (
                page_props.get("projects")
                or page_props.get("newProjects")
                or page_props.get("featuredProjects")
                or []
            )

        # Deep search fallback
        if not raw_projects:
            for key, val in page_props.items():
                if isinstance(val, dict):
                    for subkey, subval in val.items():
                        if isinstance(subval, dict):
                            for subsubkey, subsubval in subval.items():
                                if isinstance(subsubval, list) and subsubval and isinstance(subsubval[0], dict):
                                    sample = subsubval[0]
                                    if any(k in sample for k in ["title", "developer", "startingPrice", "deliveryDate"]):
                                        raw_projects = subsubval
                                        print(f"  → Found projects under: {key}.{subkey}.{subsubkey}")
                                        break

        for p in raw_projects:
            dev = p.get("developer", {})
            loc = p.get("location", {})
            price_range = p.get("priceRange", {})
            projects.append({
                "project_id": p.get("id") or p.get("project_id"),
                "name": p.get("title") or p.get("name") or p.get("project_name", ""),
                "developer": dev.get("name") if isinstance(dev, dict) else dev,
                "status": p.get("constructionPhase") or p.get("status", ""),
                "location": loc.get("fullName") or loc.get("full_name") or (loc.get("name", "") if isinstance(loc, dict) else loc),
                "starting_price": p.get("startingPrice") or p.get("starting_price") or p.get("price_from"),
                "price_min": price_range.get("min") if isinstance(price_range, dict) else None,
                "price_max": price_range.get("max") if isinstance(price_range, dict) else None,
                "currency": p.get("currency", "EGP"),
                "delivery_date": p.get("deliveryDate") or p.get("delivery_date"),
                "property_types": ", ".join(p.get("propertyTypes", [])) if isinstance(p.get("propertyTypes"), list) else "",
                "url": p.get("shareUrl") or p.get("url") or p.get("link", ""),
            })

        print(f"  ✓ Scraped {len(projects)} projects")

        # If __NEXT_DATA__ was sparse, also dump the raw keys for debugging
        if not projects:
            print("  ℹ pageProps keys:", list(page_props.keys()))
            # Save raw data for inspection
            with open("debug_projects_pageprops.json", "w", encoding="utf-8") as f:
                json.dump(page_props, f, indent=2, ensure_ascii=False, default=str)
            print("  ℹ Saved raw pageProps to debug_projects_pageprops.json")

        return projects

    # ------------------------------------------------------------------
    # JSON-LD based listing extraction (backup / enrichment)
    # ------------------------------------------------------------------
    def scrape_listings_from_jsonld(self, pages=3):
        """
        Alternative extractor that reads the serp-schema JSON-LD block.
        This contains rich structured data (amenities, geo, descriptions).
        """
        all_listings = []

        for page_num in range(1, pages + 1):
            url = (
                f"{self.BASE_URL}/rent/cairo/apartments-for-rent.html"
                f"?page={page_num}"
            )
            print(f"📄 [JSON-LD] Fetching page {page_num}: {url}")
            self.driver.get(url)
            time.sleep(3)

            schemas = self._get_jsonld_schemas()
            serp = None
            for s in schemas:
                if s.get("@id") == "SearchResultsPage":
                    serp = s
                    break

            if not serp:
                print("  ⚠ No serp-schema found – skipping")
                continue

            items = (
                serp.get("accessModeSufficient", {}).get("itemListElement", [])
            )

            for item in items:
                entity = item.get("mainEntity", {})
                address = entity.get("address", {})
                floor = entity.get("floorSize", {})
                offers = entity.get("offers", [{}])
                price_spec = offers[0].get("priceSpecification", {}) if offers else {}
                agency = offers[0].get("offeredBy", {}) if offers else {}
                geo = entity.get("geo", {})

                amenities = [
                    a["name"]
                    for a in entity.get("amenityFeature", [])
                    if a.get("value")
                ]

                listing = {
                    "listing_id": entity.get("@id"),
                    "title": entity.get("name", ""),
                    "description": (entity.get("description", "") or "")[:200],
                    "price": price_spec.get("price"),
                    "currency": price_spec.get("priceCurrency", "EGP"),
                    "price_period": price_spec.get("unitText", ""),
                    "size_sqm": floor.get("value"),
                    "location_full": address.get("name", ""),
                    "location_region": address.get("addressRegion", ""),
                    "location_city": address.get("addressLocality", ""),
                    "latitude": geo.get("latitude"),
                    "longitude": geo.get("longitude"),
                    "agency_name": agency.get("name", ""),
                    "agency_email": agency.get("email", ""),
                    "agency_phone": agency.get("telephone", ""),
                    "amenities": ", ".join(amenities),
                    "image_url": entity.get("image", ""),
                    "url": entity.get("url", ""),
                    "position": item.get("position"),
                }
                all_listings.append(listing)

            print(f"  ✓ Got {len(items)} listings from page {page_num}")

        print(f"\n✅ Total JSON-LD listings scraped: {len(all_listings)}")
        return all_listings

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def save_json(self, data, filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved {len(data)} records → {filename}")

    def save_excel(self, data, filename):
        df = pd.DataFrame(data)
        df.to_excel(filename, index=False, engine="openpyxl")
        print(f"💾 Saved {len(data)} records → {filename}")

    def close(self):
        self.driver.quit()


# ======================================================================
# Main entry point
# ======================================================================
if __name__ == "__main__":
    from generate_report import generate_report

    # --report-only: just regenerate HTML from existing JSON files
    if "--report-only" in sys.argv:
        print("📊 Generating report from existing JSON files...")
        generate_report(data_dir=".")
        sys.exit(0)

    PAGES_TO_SCRAPE = 3  # change to scrape more pages (25 listings / page)

    scraper = PropertyFinderScraper(headless=True)
    try:
        # --- Method 1: __NEXT_DATA__ (fast, structured) ---
        print("=" * 60)
        print("METHOD 1: Extracting from __NEXT_DATA__ (Next.js payload)")
        print("=" * 60)
        listings = scraper.scrape_listings(pages=PAGES_TO_SCRAPE)
        if listings:
            scraper.save_json(listings, "propertyfinder_selenium_listings.json")
            scraper.save_excel(listings, "propertyfinder_selenium_listings.xlsx")

        # --- Method 2: JSON-LD (richer data: amenities, descriptions) ---
        print("\n" + "=" * 60)
        print("METHOD 2: Extracting from JSON-LD schema (rich data)")
        print("=" * 60)
        rich_listings = scraper.scrape_listings_from_jsonld(pages=PAGES_TO_SCRAPE)
        if rich_listings:
            scraper.save_json(rich_listings, "propertyfinder_jsonld_listings.json")
            scraper.save_excel(rich_listings, "propertyfinder_jsonld_listings.xlsx")

        # --- Projects ---
        print("\n" + "=" * 60)
        print("PROJECTS")
        print("=" * 60)
        projects = scraper.scrape_projects()
        if projects:
            scraper.save_json(projects, "propertyfinder_selenium_projects.json")

        # --- Agencies ---
        print("\n" + "=" * 60)
        print("AGENCIES")
        print("=" * 60)
        agencies = scraper.scrape_agencies()
        if agencies:
            scraper.save_json(agencies, "propertyfinder_selenium_agencies.json")

        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Listings (__NEXT_DATA__):  {len(listings)}")
        print(f"  Listings (JSON-LD):        {len(rich_listings)}")
        print(f"  Projects:                  {len(projects)}")
        print(f"  Agencies:                  {len(agencies)}")

        # --- Generate HTML Report ---
        print("\n" + "=" * 60)
        print("GENERATING HTML REPORT")
        print("=" * 60)
        generate_report(
            listings=listings,
            projects=projects,
            agencies=agencies,
            output_path="propertyfinder_report.html",
        )

    finally:
        scraper.close()

