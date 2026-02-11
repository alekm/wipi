"""
Scenario Manager Service - Manages scenario definitions.
"""
import logging
import json
import os
import yaml
import uuid
from typing import List, Optional, Dict
from pathlib import Path
from sqlalchemy.orm import Session

from shared.models import Scenario
from ..models import ScenarioModel

logger = logging.getLogger(__name__)


class ScenarioManager:
    """Manages scenario definitions and storage"""

    def __init__(self, scenario_dir: str = "./scenarios"):
        """
        Initialize Scenario Manager.

        Args:
            scenario_dir: Directory containing scenario YAML files
        """
        self.scenario_dir = Path(scenario_dir)
        self.scenario_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"ScenarioManager initialized with scenario_dir: {scenario_dir}")

    def create_scenario(self, db: Session, scenario: Scenario) -> Scenario:
        """
        Create a new scenario.

        Args:
            db: Database session
            scenario: Scenario definition

        Returns:
            Created scenario with ID
        """
        try:
            # Generate ID if not provided
            if not scenario.id:
                scenario.id = str(uuid.uuid4())

            # Check if scenario with this ID already exists
            existing = db.query(ScenarioModel).filter(
                ScenarioModel.scenario_id == scenario.id
            ).first()

            if existing:
                raise ValueError(f"Scenario with ID {scenario.id} already exists")

            # Create database model
            db_scenario = ScenarioModel(
                scenario_id=scenario.id,
                name=scenario.name,
                description=scenario.description,
                definition=scenario.model_dump_json()
            )

            db.add(db_scenario)
            db.commit()
            db.refresh(db_scenario)

            logger.info(f"Created scenario: {scenario.name} ({scenario.id})")

            # Optionally save to YAML file
            self._save_scenario_to_file(scenario)

            return self._db_model_to_scenario(db_scenario)

        except Exception as e:
            logger.error(f"Error creating scenario: {e}")
            db.rollback()
            raise

    def get_scenario(self, db: Session, scenario_id: str) -> Optional[Scenario]:
        """
        Get a scenario by ID.

        Args:
            db: Database session
            scenario_id: Scenario ID

        Returns:
            Scenario or None
        """
        db_scenario = db.query(ScenarioModel).filter(
            ScenarioModel.scenario_id == scenario_id
        ).first()

        if db_scenario:
            return self._db_model_to_scenario(db_scenario)
        return None

    def get_all_scenarios(self, db: Session) -> List[Scenario]:
        """
        Get all scenarios.

        Args:
            db: Database session

        Returns:
            List of scenarios
        """
        db_scenarios = db.query(ScenarioModel).all()
        return [self._db_model_to_scenario(s) for s in db_scenarios]

    def update_scenario(self, db: Session, scenario_id: str, scenario: Scenario) -> Optional[Scenario]:
        """
        Update a scenario.

        Args:
            db: Database session
            scenario_id: Scenario ID to update
            scenario: Updated scenario data

        Returns:
            Updated scenario or None
        """
        try:
            db_scenario = db.query(ScenarioModel).filter(
                ScenarioModel.scenario_id == scenario_id
            ).first()

            if not db_scenario:
                return None

            # Update fields
            db_scenario.name = scenario.name
            db_scenario.description = scenario.description
            db_scenario.definition = scenario.model_dump_json()

            db.commit()
            db.refresh(db_scenario)

            logger.info(f"Updated scenario: {scenario_id}")

            # Update YAML file
            scenario.id = scenario_id
            self._save_scenario_to_file(scenario)

            return self._db_model_to_scenario(db_scenario)

        except Exception as e:
            logger.error(f"Error updating scenario {scenario_id}: {e}")
            db.rollback()
            raise

    def delete_scenario(self, db: Session, scenario_id: str) -> bool:
        """
        Delete a scenario.

        Args:
            db: Database session
            scenario_id: Scenario ID

        Returns:
            True if deleted, False otherwise
        """
        try:
            db_scenario = db.query(ScenarioModel).filter(
                ScenarioModel.scenario_id == scenario_id
            ).first()

            if not db_scenario:
                return False

            db.delete(db_scenario)
            db.commit()

            logger.info(f"Deleted scenario: {scenario_id}")

            # Delete YAML file
            self._delete_scenario_file(scenario_id)

            return True

        except Exception as e:
            logger.error(f"Error deleting scenario {scenario_id}: {e}")
            db.rollback()
            return False

    def load_scenarios_from_directory(self, db: Session) -> int:
        """
        Load all YAML scenarios from the scenario directory.

        Args:
            db: Database session

        Returns:
            Number of scenarios loaded
        """
        loaded_count = 0

        try:
            yaml_files = list(self.scenario_dir.glob("*.yaml")) + list(self.scenario_dir.glob("*.yml"))

            logger.info(f"Found {len(yaml_files)} YAML files in {self.scenario_dir}")

            for yaml_file in yaml_files:
                try:
                    with open(yaml_file, 'r') as f:
                        scenario_data = yaml.safe_load(f)

                    # Convert to Scenario model
                    scenario = Scenario(**scenario_data)

                    # Check if already exists
                    existing = None
                    if scenario.id:
                        existing = db.query(ScenarioModel).filter(
                            ScenarioModel.scenario_id == scenario.id
                        ).first()

                    if not existing:
                        # Create new scenario
                        self.create_scenario(db, scenario)
                        loaded_count += 1
                        logger.info(f"Loaded scenario from {yaml_file.name}")
                    else:
                        logger.debug(f"Scenario {scenario.id} already exists, skipping")

                except Exception as e:
                    logger.error(f"Error loading scenario from {yaml_file}: {e}")

            logger.info(f"Loaded {loaded_count} scenarios from directory")
            return loaded_count

        except Exception as e:
            logger.error(f"Error loading scenarios from directory: {e}")
            return 0

    def _save_scenario_to_file(self, scenario: Scenario) -> None:
        """Save scenario to YAML file"""
        try:
            filename = f"{scenario.id}.yaml"
            filepath = self.scenario_dir / filename

            # Convert scenario to dict for YAML
            scenario_dict = scenario.model_dump(exclude_none=True)

            with open(filepath, 'w') as f:
                yaml.dump(scenario_dict, f, default_flow_style=False, sort_keys=False)

            logger.debug(f"Saved scenario to {filepath}")

        except Exception as e:
            logger.error(f"Error saving scenario to file: {e}")

    def _delete_scenario_file(self, scenario_id: str) -> None:
        """Delete scenario YAML file"""
        try:
            filename = f"{scenario_id}.yaml"
            filepath = self.scenario_dir / filename

            if filepath.exists():
                filepath.unlink()
                logger.debug(f"Deleted scenario file {filepath}")

        except Exception as e:
            logger.error(f"Error deleting scenario file: {e}")

    def _db_model_to_scenario(self, db_scenario: ScenarioModel) -> Scenario:
        """Convert database model to Scenario"""
        try:
            scenario_dict = json.loads(db_scenario.definition)
            scenario = Scenario(**scenario_dict)
            scenario.created_at = db_scenario.created_at
            scenario.updated_at = db_scenario.updated_at
            return scenario

        except Exception as e:
            logger.error(f"Error converting DB model to Scenario: {e}")
            raise

    def validate_scenario(self, scenario: Scenario, available_pis: List[str]) -> Dict[str, any]:
        """
        Validate a scenario against available Pis.

        Args:
            scenario: Scenario to validate
            available_pis: List of available Pi IDs

        Returns:
            Dict with validation results
        """
        errors = []
        warnings = []

        # Check if all Pis in scenario are available
        for pi_assignment in scenario.pis:
            if pi_assignment.pi_id not in available_pis:
                errors.append(f"Pi {pi_assignment.pi_id} not available")

        # Check for duplicate interface names on same Pi
        for pi_assignment in scenario.pis:
            interface_names = [iface.name for iface in pi_assignment.interfaces]
            if len(interface_names) != len(set(interface_names)):
                errors.append(f"Duplicate interface names on Pi {pi_assignment.pi_id}")

        # Warn if many interfaces per Pi
        for pi_assignment in scenario.pis:
            if len(pi_assignment.interfaces) > 8:
                warnings.append(
                    f"Pi {pi_assignment.pi_id} has {len(pi_assignment.interfaces)} interfaces "
                    f"(may exceed hardware limits)"
                )

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }
