#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""
CLI entry point for cuems-editor WebSocket server.

Runs in foreground mode, designed for systemd services (Type=simple).
Systemd handles process supervision, logging (journald), and restart.

Example systemd service:
    [Service]
    Type=simple
    ExecStart=/usr/lib/cuems/bin/cuems-editor --port 9092
    Restart=always
"""

import sys
import os
import fcntl
import uuid
import json
import argparse

# Add src directory to path for development (when not installed)
if __name__ == '__main__' and __package__ is None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    src_dir = os.path.dirname(current_dir)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

from cuemsutils.log import Logger
from cuemsutils.tools.ConfigManager import ConfigManager, ProjectMappings
from cuemseditor.CuemsWsServer import CuemsWsServer


def get_settings():
    """Get server settings configuration"""
    settings_dict = {}
    settings_dict['session_uuid'] = str(uuid.uuid1())
    settings_dict['library_path'] = '/opt/cuems_library'
    settings_dict['tmp_path'] = '/tmp/cuems'
    settings_dict['database_name'] = 'project-manager.db'
    settings_dict['project_folder_name'] = 'projects'
    settings_dict['script_file_name'] = 'script.xml'
    settings_dict['script_schema_name'] = 'script'
    settings_dict['media_folder_name'] = 'media'
    settings_dict['trash_folder_name'] = 'trash'
    settings_dict['thumbnail_folder_name'] = 'thumbnails'
    settings_dict['waveform_folder_name'] = 'waveforms'
    settings_dict['thumbnail_extension'] = '.png'
    settings_dict['waveform_extension'] = '.dat'
    settings_dict['thumbnail_size'] = (240, 240)
    settings_dict['editor_ipc'] = '/tmp/editor.ipc'
    # Parent of the exports folder (cuems-common creates, serves and cleans
    # /var/lib/cuems/exports); not a web root any more (1amfwm7kana).
    settings_dict['html_root_path'] = '/var/lib/cuems'
    settings_dict['export_folder_name'] = 'exports'
    # Present only while apache serves /exports; export() refuses without it.
    settings_dict['export_conf_path'] = '/etc/apache2/conf-enabled/cuems-exports.conf'
    return settings_dict


def get_mappings():
    """Load project mappings configuration"""
    cf_manager = ConfigManager(load_all=False)
    settings_file = cf_manager.conf_path('default_mappings.xml')
    project_mappings = ProjectMappings(settings_file)
    return project_mappings.get_dict()


def ensure_directories(settings_dict):
    """Ensure required directories exist"""
    try:
        if not os.path.exists(settings_dict['tmp_path']):
            os.makedirs(settings_dict['tmp_path'], exist_ok=True)
            Logger.info(f"Created tmp upload folder: {settings_dict['tmp_path']}")
    except Exception as e:
        Logger.error(f"Error creating tmp folder: {type(e).__name__}: {e}")
        raise
    sweep_export_parts(settings_dict)


def sweep_export_parts(settings_dict):
    """Remove the ``.part`` files an export killed in mid-write left behind.

    Lists the exports folder with ``os.scandir`` (a glob does not see the
    dot-files every ``.<name>.XXXX.part`` is). Never creates the folder:
    cuems-common owns it, and the export refuses (E1) when it is missing.
    A running export holds a lock on its ``.part``: this runs before the port is
    bound, so a second editor started by hand must not remove that one.
    """
    folder = os.path.join(settings_dict['html_root_path'], settings_dict['export_folder_name'])
    try:
        if not os.path.isdir(folder):
            return
        with os.scandir(folder) as entries:
            parts = [e.path for e in entries if e.name.endswith('.part') and e.is_file(follow_symlinks=False)]
        for path in parts:
            _remove_unfinished_export(path)
    except Exception as e:
        Logger.error(f"Error sweeping the exports folder {folder}: {type(e).__name__}: {e}")


def _remove_unfinished_export(path):
    """Remove one ``.part`` unless a running export holds its lock."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.remove(path)
            Logger.info(f"Removed unfinished export: {path}")
        finally:
            os.close(fd)
    except BlockingIOError:
        Logger.info(f"Export still being written by another editor, left alone: {path}")
    except OSError as e:
        Logger.error(f"Error removing the unfinished export {path}: {type(e).__name__}: {e}")


def run_manual(port=9092):
    """Run server in foreground mode"""
    Logger.info("Starting CUEMS Editor")
    
    # Get configuration
    settings_dict = get_settings()
    mappings_dict = get_mappings()
    
    Logger.info(f"Project mappings: {json.dumps(mappings_dict)}")
    
    # Ensure directories
    ensure_directories(settings_dict)
    
    # Create and start server
    Logger.info(f"Starting WebSocket server on port {port}")
    server = CuemsWsServer(settings_dict, mappings_dict)
    
    try:
        server.start(port)
    except KeyboardInterrupt:
        Logger.info("Received interrupt signal, stopping server...")
    except Exception as e:
        Logger.error(f"Server error: {type(e).__name__}: {e}")
        raise


def main():
    """Main entry point - run editor in foreground"""
    parser = argparse.ArgumentParser(
        description='CUEMS Editor WebSocket Server',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Runs in foreground mode. Designed for systemd services (Type=simple).
Use Ctrl+C to stop when running manually.

Examples:
  %(prog)s
  %(prog)s --port 9092
        """
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=9092,
        help='WebSocket server port. Default: 9092'
    )
    
    args = parser.parse_args()
    run_manual(port=args.port)


if __name__ == '__main__':
    main()
