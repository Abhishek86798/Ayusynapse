#!/usr/bin/env python3
"""
Clinical Trial Matching Web Application
Simple Flask app for uploading trial criteria and patient reports
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
import traceback

# Add parent directory to path to import ayusynapse modules
sys.path.append(str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd

# Import ayusynapse modules
from ayusynapse.fhir.extractor import FHIRExtractor
from ayusynapse.fhir.converter import FHIRConverter
from ayusynapse.matcher.features import FeatureExtractor
from ayusynapse.matcher.predicates import PredicateEvaluator
from ayusynapse.matcher.engine import MatchingEngine
from ayusynapse.matcher.explain import TrialExplainer
from ayusynapse.matcher.rank import TrialRanker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change in production

# Configuration
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'json'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Ensure upload directory exists
UPLOAD_FOLDER.mkdir(exist_ok=True)

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_trial_criteria(file_path):
    """Process trial criteria file and extract FHIR data"""
    try:
        extractor = FHIRExtractor()
        extracted_data = extractor.extract_from_file(str(file_path))
        
        converter = FHIRConverter()
        fhir_bundle = converter.convert_to_fhir(extracted_data)
        
        return {
            'success': True,
            'extracted_data': extracted_data,
            'fhir_bundle': fhir_bundle,
            'trials_count': len(extracted_data.get('trials', []))
        }
    except Exception as e:
        logger.error(f"Error processing trial criteria: {e}")
        return {
            'success': False,
            'error': str(e)
        }

def process_patient_reports(file_paths):
    """Process multiple patient report files"""
    results = []
    
    for file_path in file_paths:
        try:
            # For now, create a simple patient FHIR bundle
            # In production, you'd use the NER pipeline here
            patient_bundle = create_sample_patient_bundle(file_path)
            
            results.append({
                'filename': file_path.name,
                'success': True,
                'patient_bundle': patient_bundle
            })
        except Exception as e:
            logger.error(f"Error processing patient report {file_path}: {e}")
            results.append({
                'filename': file_path.name,
                'success': False,
                'error': str(e)
            })
    
    return results

def create_sample_patient_bundle(file_path):
    """Create a sample patient FHIR bundle for demonstration"""
    # This is a simplified version - in production, you'd use the NER pipeline
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": "patient-1",
                    "gender": "female",
                    "birthDate": "1980-01-01"
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "id": "condition-1",
                    "code": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "363418001",
                                "display": "Biliary cancer"
                            }
                        ]
                    }
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs-1",
                    "code": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "HER2",
                                "display": "HER2 Status"
                            }
                        ]
                    },
                    "valueCodeableConcept": {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "positive",
                                "display": "Positive"
                            }
                        ],
                        "text": "Positive"
                    }
                }
            }
        ]
    }

def match_patients_to_trials(patient_bundles, trial_data):
    """Match patients to trials using the matching pipeline"""
    try:
        # Initialize components
        feature_extractor = FeatureExtractor()
        predicate_evaluator = PredicateEvaluator()
        matching_engine = MatchingEngine()
        explainer = TrialExplainer()
        ranker = TrialRanker()
        
        all_results = []
        
        for patient_data in patient_bundles:
            if not patient_data['success']:
                continue
                
            patient_bundle = patient_data['patient_bundle']
            patient_filename = patient_data['filename']
            
            # Extract patient features
            patient_features = feature_extractor.extract_patient_features(patient_bundle)
            
            # For each trial in the criteria
            trial_results = []
            for trial in trial_data['extracted_data'].get('trials', []):
                # Create trial predicates (simplified)
                trial_predicates = {
                    'inclusion': [
                        {
                            'type': 'Observation',
                            'field': 'HER2',
                            'op': '==',
                            'value': 'positive',
                            'weight': 3
                        },
                        {
                            'type': 'Condition',
                            'code': '363418001',  # Biliary cancer
                            'op': 'present',
                            'weight': 5
                        }
                    ],
                    'exclusion': [
                        {
                            'type': 'Condition',
                            'code': '128462008',  # CNS metastases
                            'op': 'present',
                            'weight': 10
                        }
                    ]
                }
                
                # Evaluate trial
                result = matching_engine.evaluate_trial(patient_features, trial_predicates)
                
                # Create explanation
                explanation = explainer.make_explanation(result)
                
                trial_results.append({
                    'trial_id': trial.get('id', 'Unknown'),
                    'trial_title': trial.get('title', 'Unknown Trial'),
                    'result': result,
                    'explanation': explanation
                })
            
            # Rank trials
            ranked_trials = ranker.rank_trials(trial_results, min_score=60)
            
            all_results.append({
                'patient_filename': patient_filename,
                'ranked_trials': ranked_trials
            })
        
        return {
            'success': True,
            'results': all_results
        }
        
    except Exception as e:
        logger.error(f"Error in matching pipeline: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/')
def index():
    """Main page with file upload forms"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle file uploads and process matching"""
    try:
        # Check if trial criteria file was uploaded
        if 'trial_criteria' not in request.files:
            flash('No trial criteria file selected', 'error')
            return redirect(request.url)
        
        trial_file = request.files['trial_criteria']
        if trial_file.filename == '':
            flash('No trial criteria file selected', 'error')
            return redirect(request.url)
        
        # Check if patient reports were uploaded
        patient_files = request.files.getlist('patient_reports')
        if not patient_files or patient_files[0].filename == '':
            flash('No patient report files selected', 'error')
            return redirect(request.url)
        
        # Validate files
        if not allowed_file(trial_file.filename):
            flash('Invalid trial criteria file type', 'error')
            return redirect(request.url)
        
        for patient_file in patient_files:
            if not allowed_file(patient_file.filename):
                flash(f'Invalid patient report file type: {patient_file.filename}', 'error')
                return redirect(request.url)
        
        # Save files
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        trial_filename = secure_filename(f"trial_criteria_{timestamp}_{trial_file.filename}")
        trial_path = UPLOAD_FOLDER / trial_filename
        trial_file.save(str(trial_path))
        
        patient_paths = []
        for i, patient_file in enumerate(patient_files):
            patient_filename = secure_filename(f"patient_{i}_{timestamp}_{patient_file.filename}")
            patient_path = UPLOAD_FOLDER / patient_filename
            patient_file.save(str(patient_path))
            patient_paths.append(patient_path)
        
        # Process trial criteria
        logger.info("Processing trial criteria...")
        trial_result = process_trial_criteria(trial_path)
        
        if not trial_result['success']:
            flash(f'Error processing trial criteria: {trial_result["error"]}', 'error')
            return redirect(request.url)
        
        # Process patient reports
        logger.info("Processing patient reports...")
        patient_results = process_patient_reports(patient_paths)
        
        # Match patients to trials
        logger.info("Matching patients to trials...")
        matching_result = match_patients_to_trials(patient_results, trial_result)
        
        if not matching_result['success']:
            flash(f'Error in matching pipeline: {matching_result["error"]}', 'error')
            return redirect(request.url)
        
        # Store results in session for display
        session_data = {
            'trial_info': {
                'filename': trial_filename,
                'trials_count': trial_result['trials_count']
            },
            'patient_files': [p.name for p in patient_paths],
            'matching_results': matching_result['results']
        }
        
        # For simplicity, we'll pass results directly to template
        return render_template('results.html', 
                             trial_info=session_data['trial_info'],
                             patient_files=session_data['patient_files'],
                             matching_results=session_data['matching_results'])
        
    except Exception as e:
        logger.error(f"Error in upload handler: {e}")
        traceback.print_exc()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(request.url)

@app.route('/api/match', methods=['POST'])
def api_match():
    """API endpoint for programmatic matching"""
    try:
        data = request.get_json()
        
        if not data or 'trial_criteria' not in data or 'patient_reports' not in data:
            return jsonify({'error': 'Missing required data'}), 400
        
        # Process the data (simplified for API)
        # In production, you'd implement the full pipeline here
        
        return jsonify({
            'success': True,
            'message': 'API matching endpoint - implement full pipeline here'
        })
        
    except Exception as e:
        logger.error(f"Error in API match: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
