from setuptools import setup, find_packages

setup(
    name="internpilot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.7",
        "pyyaml>=6.0.1",
        "python-dotenv>=1.0.0",
        "jinja2>=3.1.3",
        "anthropic>=0.39.0",
        "langchain-anthropic>=0.3.3",
        "browser-use>=0.1.40",
        "playwright>=1.49.0",
        "python-jobspy>=1.1.80",
        "python-docx>=1.1.0",
        "google-api-python-client>=2.153.0",
        "google-auth>=2.35.0",
        "google-auth-httplib2>=0.2.0",
        "google-auth-oauthlib>=1.2.1",
        "apscheduler>=3.10.4",
        "requests>=2.32.3",
    ],
    entry_points={
        "console_scripts": [
            "internpilot=src.cli:cli",
        ],
    },
    python_requires=">=3.11",
)
