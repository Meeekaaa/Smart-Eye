# Smart Eye

**An Intelligent Safety Surveillance System**

Smart Eye is an open-source, AI-powered surveillance system that uses computer vision to automate safety monitoring in real time. It combines object detection, face detection, face recognition, and Personal Protective Equipment (PPE) detection into a single, modular application designed for industrial, construction, and other safety-critical environments.

---

## Features

- **Object Detection** — Detects and localizes people and relevant objects in a video stream.
- **Face Detection & Recognition** — Identifies and verifies individuals against a known database.
- **PPE Detection** — Checks whether required safety gear (e.g., helmets, vests) is being worn and flags violations.
- **Real-Time Inference** — Runs deep learning models through ONNX Runtime for fast, cross-platform performance.
- **Modular Architecture** — Cleanly separated backend, frontend, and data layers for easy extension and maintenance.
- **Automated Testing & CI** — GitHub Actions workflows help maintain code quality.

---

## Project Structure

```
Smart-Eye/
├── .github/workflows/   # CI/CD pipelines
├── backend/             # Detection & recognition pipelines, core logic
├── frontend/            # User interface and visualization
├── data/                # Datasets, models, and supporting data
├── scripts/             # Utility and automation scripts
├── tests/               # Automated tests
├── utils/               # Shared helper modules
├── main.py              # Application entry point
├── build.sh             # Build script
├── requirements.txt     # Core dependencies
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.9+ (recommended)
- `pip` and `virtualenv`

### Installation

```bash
# Clone the repository
git clone https://github.com/ABO47/Smart-Eye.git
cd Smart-Eye

# (Optional) create a virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application

```bash
python main.py
```

For development, install the additional tooling:

```bash
pip install -r requirements-dev.txt
```

---

## Testing

```bash
pytest tests/
```

---

## Tech Stack

| Component        | Technology                          |
|------------------|-------------------------------------|
| Language         | Python                              |
| Inference Engine | ONNX / ONNX Runtime                 |
| Computer Vision  | Object detection, face recognition, PPE detection |
| CI/CD            | GitHub Actions                      |
| Linting          | Ruff                                |

---

## Contributing

Contributions are welcome. Please fork the repository, create a feature branch, and open a pull request. Make sure tests pass and code is formatted before submitting.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details. Third-party licenses are listed in [THIRD_PARTY_LICENSES.txt](THIRD_PARTY_LICENSES.txt).

---

## Author

Developed and maintained by [ABO47](https://github.com/ABO47).
