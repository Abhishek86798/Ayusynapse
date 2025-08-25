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
from ayusynapse.matcher.trial_processor import TrialDataProcessor
from ayusynapse.matcher.weighted_matcher import WeightedMatchingEngine, FeatureVector

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
    """Match patients to trials using the weighted matching pipeline"""
    try:
        # Initialize weighted matching processor
        processor = TrialDataProcessor()
        
        # Convert patient bundles to feature vectors
        patients = []
        for patient_data in patient_bundles:
            if not patient_data['success']:
                continue
            
            # Create feature vector from patient bundle
            patient_features = create_feature_vector_from_bundle(patient_data['patient_bundle'])
            patients.append(patient_features)
        
        # Convert trial data to feature vectors
        trials = []
        for trial in trial_data['extracted_data'].get('trials', []):
            # Create feature vector from trial data
            trial_features = create_feature_vector_from_trial(trial)
            trials.append(trial_features)
        
        if not patients or not trials:
            return {
                'success': False,
                'error': 'No valid patients or trials found'
            }
        
        # Initialize and run weighted matching
        processor.initialize_matching_engine(patients, trials)
        results = processor.match_patients_to_trials(patients, trials)
        
        # Convert results to expected format
        all_results = []
        for i, patient_results in enumerate(results):
            if i < len(patient_bundles):
                patient_filename = patient_bundles[i]['filename']
            else:
                patient_filename = f"patient_{i}"
            
            # Convert weighted matching results to trial results format
            trial_results = []
            for result in patient_results:
                trial_results.append({
                    'trial_id': f"trial_{result['trial_index']}",
                    'trial_title': f"Trial {result['trial_index']}",
                    'result': {
                        'score': result['match_score'] * 100,  # Convert to percentage
                        'eligible': result['is_eligible'],
                        'confidence': result['confidence']
                    },
                    'explanation': {
                        'feature_contributions': result['feature_contributions'],
                        'match_score': result['match_score'],
                        'confidence': result['confidence']
                    }
                })
            
            # Sort by score
            trial_results.sort(key=lambda x: x['result']['score'], reverse=True)
            
            all_results.append({
                'patient_filename': patient_filename,
                'ranked_trials': trial_results
            })
        
        return {
            'success': True,
            'results': all_results
        }
        
    except Exception as e:
        logger.error(f"Error in weighted matching pipeline: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }

def create_feature_vector_from_bundle(bundle):
    """Create FeatureVector from FHIR bundle"""
    features = FeatureVector()
    
    # Extract patient information
    for entry in bundle.get('entry', []):
        resource = entry.get('resource', {})
        resource_type = resource.get('resourceType')
        
        if resource_type == 'Patient':
            # Extract age and gender
            if 'birthDate' in resource:
                birth_date = resource['birthDate']
                # Simple age calculation (in production, use proper date parsing)
                features.age = 50  # Placeholder
            
            if 'gender' in resource:
                features.gender = resource['gender']
        
        elif resource_type == 'Condition':
            # Extract disease information
            if 'code' in resource and 'coding' in resource['code']:
                for coding in resource['code']['coding']:
                    if 'display' in coding:
                        features.disease = coding['display'].lower()
                        break
        
        elif resource_type == 'Observation':
            # Extract biomarkers and lab values
            if 'code' in resource and 'coding' in resource['code']:
                for coding in resource['code']['coding']:
                    if 'code' in coding:
                        code = coding['code']
                        if code in ['HER2', 'ER', 'PR', 'BRCA1', 'BRCA2']:
                            features.biomarkers.append(code)
                        else:
                            # Store as lab value
                            if 'valueQuantity' in resource:
                                features.lab_values[code] = resource['valueQuantity']['value']
    
    return features

def create_feature_vector_from_trial(trial_data):
    """Create FeatureVector from trial data"""
    features = FeatureVector()
    
    # Extract trial information
    if 'title' in trial_data:
        title = trial_data['title'].lower()
        if 'cancer' in title or 'carcinoma' in title:
            features.disease = 'cancer'
        elif 'diabetes' in title:
            features.disease = 'diabetes'
    
    if 'inclusion_criteria' in trial_data:
        criteria = trial_data['inclusion_criteria'].lower()
        
        # Extract age requirements
        import re
        age_match = re.search(r'(\d+)\s*-\s*(\d+)\s*years?', criteria)
        if age_match:
            min_age = float(age_match.group(1))
            max_age = float(age_match.group(2))
            features.age = (min_age + max_age) / 2
        
        # Extract biomarkers
        for biomarker in ['HER2', 'ER', 'PR', 'BRCA1', 'BRCA2']:
            if biomarker.lower() in criteria:
                features.biomarkers.append(biomarker)
    
    return features

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
