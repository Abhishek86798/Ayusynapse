#!/usr/bin/env python3
"""
Simple Clinical Trial Matching Web Application
Basic version for testing the interface
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
from database import db

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

def create_demo_results():
    """Create demo results for testing"""
    return {
        'trial_info': {
            'filename': 'demo_trial_criteria.docx',
            'trials_count': 3
        },
        'patient_files': ['patient_1.pdf', 'patient_2.pdf'],
        'matching_results': [
            {
                'patient_filename': 'patient_1.pdf',
                'ranked_trials': [
                    {
                        'trial_id': 'NCT07062263',
                        'trial_title': 'HER2+ Biliary Cancer Treatment Study',
                        'result': {
                            'eligible': True,
                            'score': 85.5,
                            'matched': [
                                'HER2 status: Positive',
                                'Cancer type: Biliary cancer',
                                'Age: 55 years (≥18 required)'
                            ],
                            'unmatched': [
                                'ECOG performance status: 1 (≤2 required)'
                            ],
                            'missing': [
                                'Recent CBC results',
                                'Liver function tests'
                            ],
                            'exclusions_triggered': [],
                            'suggested_data': [
                                'Order complete blood count (CBC)',
                                'Perform liver function panel',
                                'Assess ECOG performance status'
                            ]
                        },
                        'explanation': {
                            'summary': 'Patient is eligible for this trial with high match score.',
                            'matched_facts': 'HER2 positive status and biliary cancer diagnosis match trial requirements.',
                            'blockers': 'None - patient meets all critical inclusion criteria.',
                            'recommendations': 'Consider additional lab tests for comprehensive assessment.'
                        }
                    },
                    {
                        'trial_id': 'NCT12345678',
                        'trial_title': 'Advanced Cancer Immunotherapy Trial',
                        'result': {
                            'eligible': False,
                            'score': 45.2,
                            'matched': [
                                'Age: 55 years (≥18 required)'
                            ],
                            'unmatched': [
                                'Cancer type: Requires lung cancer',
                                'PD-L1 expression: Not tested'
                            ],
                            'missing': [
                                'PD-L1 expression test',
                                'Tumor mutation burden'
                            ],
                            'exclusions_triggered': [],
                            'suggested_data': [
                                'Perform PD-L1 immunohistochemistry',
                                'Test for tumor mutation burden',
                                'Confirm cancer type diagnosis'
                            ]
                        },
                        'explanation': {
                            'summary': 'Patient does not meet primary cancer type requirement.',
                            'matched_facts': 'Age requirement is met.',
                            'blockers': 'Cancer type mismatch and missing biomarker data.',
                            'recommendations': 'Consider trials specific to biliary cancer.'
                        }
                    }
                ]
            },
            {
                'patient_filename': 'patient_2.pdf',
                'ranked_trials': [
                    {
                        'trial_id': 'NCT87654321',
                        'trial_title': 'General Oncology Treatment Study',
                        'result': {
                            'eligible': True,
                            'score': 72.8,
                            'matched': [
                                'Age: 62 years (≥18 required)',
                                'No CNS metastases'
                            ],
                            'unmatched': [
                                'Specific biomarker: Not tested'
                            ],
                            'missing': [
                                'Biomarker panel results'
                            ],
                            'exclusions_triggered': [],
                            'suggested_data': [
                                'Order comprehensive biomarker panel',
                                'Perform genetic testing'
                            ]
                        },
                        'explanation': {
                            'summary': 'Patient is eligible with moderate match score.',
                            'matched_facts': 'Age and absence of CNS metastases meet requirements.',
                            'blockers': 'Missing biomarker data reduces score.',
                            'recommendations': 'Additional testing could improve match score.'
                        }
                    }
                ]
            }
        ]
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
        
        logger.info(f"Files uploaded: {trial_filename}, {len(patient_paths)} patient files")
        
        # For demo purposes, return mock results
        # In production, you'd call the actual matching pipeline here
        demo_results = create_demo_results()
        
        # Save to database
        try:
            upload_id = db.save_upload(trial_filename, [p.name for p in patient_paths])
            db.save_results(upload_id, demo_results['matching_results'])
            logger.info(f"Saved to database with upload ID: {upload_id}")
        except Exception as e:
            logger.error(f"Database save error: {e}")
            # Continue without database if there's an error
        
        return render_template('results.html', 
                             trial_info=demo_results['trial_info'],
                             patient_files=[p.name for p in patient_paths],
                             matching_results=demo_results['matching_results'],
                             current_time=datetime.now().strftime('%B %d, %Y, %I:%M %p'))
        
    except Exception as e:
        logger.error(f"Error in upload handler: {e}")
        traceback.print_exc()
        flash(f'An error occurred: {str(e)}', 'error')
        return redirect(request.url)

@app.route('/history')
def upload_history():
    """View upload history"""
    try:
        uploads = db.get_upload_history(limit=20)
        stats = db.get_statistics()
        return render_template('history.html', uploads=uploads, stats=stats)
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return render_template('history.html', uploads=[], stats={})

@app.route('/results/<int:upload_id>')
def view_results(upload_id):
    """View results for a specific upload"""
    try:
        results = db.get_results_by_upload(upload_id)
        uploads = db.get_upload_history(limit=1)
        upload_info = next((u for u in uploads if u['id'] == upload_id), None)
        
        if not upload_info:
            flash('Upload not found', 'error')
            return redirect(url_for('upload_history'))
        
        return render_template('results.html', 
                             trial_info={'filename': upload_info['trial_file'], 'trials_count': len(set(r['trial_id'] for r in results))},
                             patient_files=upload_info['patient_files'],
                             matching_results=results,
                             current_time=datetime.fromisoformat(upload_info['timestamp']).strftime('%B %d, %Y, %I:%M %p'))
    except Exception as e:
        logger.error(f"Error getting results: {e}")
        flash('Error loading results', 'error')
        return redirect(url_for('upload_history'))

@app.route('/api/match', methods=['POST'])
def api_match():
    """API endpoint for programmatic matching"""
    try:
        data = request.get_json()
        
        if not data or 'trial_criteria' not in data or 'patient_reports' not in data:
            return jsonify({'error': 'Missing required data'}), 400
        
        # Return demo results for now
        demo_results = create_demo_results()
        
        return jsonify({
            'success': True,
            'results': demo_results
        })
        
    except Exception as e:
        logger.error(f"Error in API match: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Starting Clinical Trial Matching Web App...")
    print("📱 Open your browser and go to: http://localhost:5000")
    print("📁 Upload trial criteria and patient reports to test the system")
    app.run(debug=True, host='0.0.0.0', port=5000)
