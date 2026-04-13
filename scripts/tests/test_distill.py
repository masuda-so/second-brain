import sys
import pathlib

# Add scripts directory to path to allow importing distill
sys.path.append(str(pathlib.Path(__file__).parent.parent))

from distill import slugify

def test_slugify_normal_text():
    assert slugify("Hello World") == "hello-world"

def test_slugify_empty_string():
    assert slugify("") == "note"

def test_slugify_only_special_chars():
    assert slugify("@#$%^&*") == "note"

def test_slugify_mixed_spacing_and_underscores():
    assert slugify("  test_ _string-  ") == "test-string"

def test_slugify_non_alphanumeric_removal():
    assert slugify("test@#$string") == "teststring"

def test_slugify_long_string():
    long_string = "a" * 100
    assert len(slugify(long_string)) == 80
    assert slugify(long_string) == "a" * 80

def test_slugify_long_string_with_hyphens():
    long_string = "a " * 50
    slug = slugify(long_string)
    assert len(slug) <= 80
    assert slug.startswith("a-a-")

def test_slugify_trims_hyphens():
    assert slugify("-hello-world-") == "hello-world"
