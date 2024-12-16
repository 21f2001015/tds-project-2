# /// script
# requires-python = ">=3.11"
# dependencies = [
# "urllib3",
# "python-dotenv",
# "requests",
# "pandas",
# "matplotlib",
# "seaborn",
# "chardet"
# ]
# ///

import os, sys, json
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def detectEncoding(filename):
    try:
        import chardet
    except ImportError:
        os.system("pip install chardet")
        import chardet
    
    with open(filename, "rb") as f:
        encoding = chardet.detect(f.read())["encoding"]
    return encoding

def create_session_with_retries():
    """
    Creates a requests session with retry logic.
    """
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def analyzeData(filename):
    # Detect Character Encoding
    encoding = detectEncoding(filename)

    try:
        df = pd.read_csv(filename, encoding=encoding)
        print(f"Successfully loaded {filename} with encoding {encoding}")
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        sys.exit(1)

    # Perform analysis
    try:
        summary = df.describe(include="all").to_dict()
    except Exception as e:
        print(f"Warning: Unable to generate summary statistics for {filename}: {e}")
        summary = {}
    
    missing_values = df.isnull().sum().to_dict()
    dtypes = df.dtypes.apply(str).to_dict()
    columns = list(df.columns)

    analysis = {
        "columns": columns,
        "dtypes": dtypes,
        "missing_values": missing_values,
        "summary": summary
    }

    # Handling missing values

    # Impute numerical columns with median
    numerical = df.select_dtypes(include=['number']).columns
    for col in numerical:
        df[col].fillna(df[col].median(), inplace=True)
    
    # Impute categorical columns with mode
    categorical = df.select_dtypes(include=['object', 'category']).columns
    for col in categorical:
        if not df[col].mode().empty:
            df[col].fillna(df[col].mode().iloc[0], inplace=True)

    # Check for outliers
    outliers = {}
    for col in numerical:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers[col] = df[(df[col] < lower_bound) | (df[col] > upper_bound)].shape[0]

    analysis["outliers"] = outliers

    # Feature Selection
    features = {}
    if len(numerical) > 1:
        # Correlation matrix
        corr_matrix = df[numerical].corr()
        for col in numerical:
            correlations = corr_matrix[col].drop(labels=[col]).abs().sort_values(ascending=False)
            if not correlations.empty:
                features[col] = correlations.index[0]
            else:
                features[col] = None
    analysis["features"] = features

    return df, analysis

def visualizeData(df, outputPath):
    images = []

    # 1. Correlation Heatmap
    numerical = df.select_dtypes(include=['number']).columns
    if len(numerical) > 1:
        corr_matrix = df[numerical].corr()
        plt.figure(figsize=(12, 10))
        sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f")
        plt.title("Correlation Heatmap")
        heatmapPath = os.path.join(outputPath, "correlation_heatmap.png")
        plt.savefig(heatmapPath, dpi=100)
        plt.close()
        images.append("correlation_heatmap.png")
        print(f"Saved correlation heatmap to {heatmapPath}")

    # 2. Distribution Plot of Numerical Columns
    if len(numerical) > 0:
        firstNumColumn = numerical[0]
        plt.figure(figsize=(10, 6))
        sns.histplot(df[firstNumColumn], kde=True, bins=30, color="skyblue")
        plt.title(f"Distribution of {firstNumColumn}")
        plt.xlabel(firstNumColumn)
        plt.ylabel("Frequency")
        distPlotPath = os.path.join(outputPath, f"{firstNumColumn}_distribution.png")
        plt.savefig(distPlotPath, dpi=100)
        plt.close()
        images.append(f"{firstNumColumn}_distribution.png")
        print(f"Saved {firstNumColumn} distribution plot to {distPlotPath}")

    # 3. Categorical Count Plot
    categorical = df.select_dtypes(include=['object', 'category']).columns
    if len(categorical) > 0:
        firstCatColumn = categorical[0]
        plt.figure(figsize=(12, 8))
        sns.countplot(data=df, y=firstCatColumn,
                      order=df[firstCatColumn].value_counts().index[:10],
                      palette="viridis", dodge=False)
        plt.title(f"Top 10 {firstCatColumn} Categories")
        plt.xlabel("Count")
        plt.ylabel(firstCatColumn)
        plt.legend([], [], frameon=False)
        countPlotPath = os.path.join(outputPath, f"{firstCatColumn}_count.png")
        plt.savefig(countPlotPath, dpi=100)
        plt.close()
        images.append(f"{firstCatColumn}_count.png")
        print(f"Saved {firstCatColumn} count plot to {countPlotPath}")
    
    # 4. Box Plot of Outliers
    if len(numerical) > 0:
        firstColumn = numerical[0]
        plt.figure(figsize=(10, 6))
        sns.boxplot(x=df[firstColumn], color='lightgreen')
        plt.title(f"Box Plot of {firstColumn}")
        plt.xlabel(firstColumn)
        boxPlotPath = os.path.join(outputPath, f"{firstColumn}_boxplot.png")
        plt.savefig(boxPlotPath, dpi=100)
        plt.close()
        images.append(f"{firstColumn}_boxplot.png")
        print(f"Saved {firstColumn} box plot to {boxPlotPath}")

    return images

def narrateAnalysis(analysis, images, api_key, api_endpoint):

    session = create_session_with_retries()
    has_outliers = any(count > 0 for count in analysis["outliers"].values())

    analysisSummary = (
        f"**Columns:** {analysis['columns']}\n"
        f"**Data Types:** {analysis['dtypes']}\n"
        f"**Missing Values:** {analysis['missing_values']}\n"
        f"**Summary Statistics:** {json.dumps(analysis['summary'], indent=2)}\n"
        f"**Outliers:** {json.dumps(analysis['outliers'], indent=2)}\n"
        f"**Features:** {json.dumps(analysis['features'], indent=2)}\n"
    )

    prompt = (
        "You are an expert data scientist with extensive experience in data analysis and visualization. "
        "Based on the comprehensive analysis provided below, generate a detailed narrative in Markdown format that includes the following sections:\n\n"
        "1. **Dataset Overview:** A thorough description of the dataset, including its source, purpose, and structure.\n"
        "2. **Data Cleaning and Preprocessing:** Outline the steps taken to handle missing values, outliers, and any data transformations applied.\n"
    )

    if has_outliers:
        prompt += "3. **Outlier Analysis:** Discuss the outliers detected and their potential impact on the data.\n"
    else:
        prompt += "3. **Data Quality:** Confirm that the dataset is clean with no significant outliers detected.\n"

    prompt += (
        "4. **Exploratory Data Analysis (EDA):** Present key insights, trends, and patterns discovered during the analysis.\n"
        "5. **Visualizations:** For each generated chart, provide an in-depth explanation of what it represents and the insights it offers.\n"
    )

    prompt += (
        "7. **Implications and Recommendations:** Based on the findings, suggest actionable recommendations or potential implications for stakeholders.\n"
        "8. **Future Work:** Propose three additional analyses or visualizations that could further enhance the understanding of the dataset.\n"
        "9. **Vision Agentic Enhancements:** Recommend ways to incorporate advanced visual (image-based) analysis techniques or interactive visualizations to provide deeper insights.\n\n"
        f"**Comprehensive Analysis:**\n{analysisSummary}"
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a helpful data scientist creatively narrating the story of a dataset."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 2500,
        "temperature": 0.7,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    try:
        response = session.post(api_endpoint, headers=headers, json=payload)
        try:
            result = response.json()
            story = result['choices'][0]['message']['content']
        except ValueError:
            print(f"Invalid JSON response: {response.text}")
            story = f"Error generating narrative: Invalid JSON response"
    except Exception as e:
        print(f"Error generating narrative: {e}")
        story = f"Error generating narrative: {e}"

    # Append image references to the narrative
    if images and "error" not in story.lower():
        story += "\n\n## Visualizations\n"
        for img in images:
            if img.endswith('.html'):
                story += f"[Interactive Visualization]({img})\n"
            else:
                story += f"![{img}]({img})\n"
    
    return story

def autolysis(filename, api_key, api_endpoint):
    basePath = os.path.splitext(os.path.basename(filename))[0]
    outputPath = os.path.join(os.getcwd(), basePath)
    os.makedirs(outputPath, exist_ok=True)
    print(f"Output directory: {outputPath}")

    df, analysis = analyzeData(filename)
    images = visualizeData(df, outputPath)
    story = narrateAnalysis(analysis, images, api_key, api_endpoint)

    readmePath = os.path.join(outputPath, "README.md")
    try:
        with open(readmePath, "w", encoding="utf-8") as f:
            f.write(story)
        print(f"Saved narrative to {readmePath}")
    except Exception as e:
        print(f"Error saving narrative: {e}")

    return outputPath

def main():
    # Correct usage prompt
    if len(sys.argv) != 2:
        print("Usage: uv run autolysis.py <dataset.csv>")
        sys.exit(1)
    
    filename = sys.argv[1]

    load_dotenv()

    # OpenAI API Key
    api_key = os.getenv("AIPROXY_TOKEN")
    if not api_key:
        print("API key not found. Please set the AIPROXY_TOKEN environment variable.")
        sys.exit(1)

    # OpenAI API endpoint
    api_endpoint = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"

    if os.path.exists(filename):
        print(f"Processing {filename}")
        outputPath = autolysis(filename, api_key, api_endpoint)
        print(f"Output directory: {outputPath}")
    else:
        print(f"File {filename} not found!")

if __name__ == "__main__":
    main()