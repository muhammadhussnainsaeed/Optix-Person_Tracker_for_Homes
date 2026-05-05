from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from core import security
from db import session
from schemas import rules

router = APIRouter()

@router.get("/rules/fetch_all")
def fetch_monitoring_rules_full(
    username: str,
    jwt_token: str,
    user_id: str,
    db: Session = Depends(session.get_db)
):
    """
    Fetches all monitoring rules for a specific user, including their time constraints
    and a nested list of all cameras linked to each rule.
    """

    # 1. Standard Security Verification
    token_verification = security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    # 2. SQL Query to fetch rule data, primary person photo, and linked cameras
    query = text("""
        SELECT
            mr.id,
            mr.rule_name,
            mr.from_time,
            mr.to_time,
            mr.is_active,
            p.name AS person_name,
            -- Subquery for primary avatar photo
            (
                SELECT pp.photo_url
                FROM person_photos pp
                WHERE pp.person_id = p.id
                  AND pp.is_primary = TRUE
                LIMIT 1
            ) AS person_photo_url,
            -- Subquery to aggregate all assigned cameras for this rule
            (
                SELECT json_agg(
                    json_build_object(
                        'camera_id', c.id, 
                        'camera_name', c.name
                    )
                )
                FROM pgadmin_recover mrc
                JOIN cameras c ON mrc.camera_id = c.id
                WHERE mrc.rule_id = mr.id
            ) AS cameras
        FROM pgadmin_config mr
        JOIN persons p ON mr.person_id = p.id
        WHERE mr.user_id = :user_id
        ORDER BY mr.created_at DESC;
    """)

    # 3. Execution
    result = db.execute(query, {"user_id": user_id})
    rules_list = result.mappings().all()

    # 4. Return the exact response structure matching previous examples
    return {
        "message": "Monitoring Rules fetched successfully",
        "rules": rules_list
    }


@router.post("/rules/create")
def create_monitoring_rules(user_data: rules.MonitoringRuleCreateRequest, db: Session = Depends(session.get_db)):
    """
    Creates a single rule in 'monitoring_rules' and multiple linked camera
    entries in the 'monitoring_rule_cameras' junction table.
    """

    # 1. Standard Security Verification
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    # 2. Required Logic: Ensure there is at least one camera selected
    if not user_data.camera_ids:
        raise HTTPException(status_code=400, detail="At least one camera ID must be provided")

    try:
        # Use a transaction block to ensure all parts are committed together
        with db.begin():

            # 3. Insert rule metadata into the core table
            insert_rule_sql = text("""
                INSERT INTO pgadmin_config (
                    user_id,
                    person_id,
                    rule_name,
                    from_time,
                    to_time,
                    is_active
                )
                VALUES (
                    :user_id,
                    :person_id,
                    :rule_name,
                    :from_time,
                    :to_time,
                    :is_active
                ) RETURNING id;
            """)

            result = db.execute(insert_rule_sql, {
                "user_id": user_data.user_id,
                "person_id": user_data.person_id,
                "rule_name": user_data.rule_name,
                "from_time": user_data.from_time,
                "to_time": user_data.to_time,
                "is_active": user_data.is_active
            })

            new_rule_id = result.fetchone()[0]  # Get the UUID of the newly created rule

            # 4. Loop through the camera list and insert them into the junction table
            insert_cameras_sql = text("""
                INSERT INTO pgadmin_recover (rule_id, camera_id)
                VALUES (:rule_id, :camera_id);
            """)

            for cam_id in user_data.camera_ids:
                db.execute(insert_cameras_sql, {
                    "rule_id": new_rule_id,
                    "camera_id": cam_id
                })

    except Exception as e:
        # Handle database connection issues, foreign key constraint violations, etc.
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during creation: {str(e)}")

    # 5. Return clean response with newly created rule ID
    return {
        "message": "Monitoring rule and cameras linked successfully",
        "rule_id": str(new_rule_id)
    }

@router.post("/rules/delete")
def delete_monitoring_rule(user_data: rules.MonitoringRuleDeleteRequest, db: Session = Depends(session.get_db)):
    """
    Deletes exactly one rule.
    First removes the associated entries in monitoring_rule_cameras,
    and then deletes the core rule metadata.
    """

    # 1. Standard Security Verification
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    try:
        # Use a transaction block to make sure both deletes succeed together
        with db.begin():

            # Step A: Delete from the cameras junction table first
            delete_cameras_sql = text("""
                                      DELETE
                                      FROM pgadmin_recover
                                      WHERE rule_id = :rule_id;
                                      """)
            db.execute(delete_cameras_sql, {"rule_id": user_data.rule_id})

            # Step B: Delete the rule from the main table (secured by user_id)
            delete_rule_sql = text("""
                                   DELETE
                                   FROM pgadmin_config
                                   WHERE id = :rule_id
                                     AND user_id = :user_id;
                                   """)
            result = db.execute(delete_rule_sql, {
                "rule_id": user_data.rule_id,
                "user_id": user_data.user_id
            })

            # If the rule didn't exist or doesn't belong to the user
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Rule not found or unauthorized access")

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during deletion: {str(e)}")

    return {
        "message": "Monitoring Rule deleted successfully",
        "rule_id": str(user_data.rule_id)
    }


@router.post("/rules/toggle")
def toggle_monitoring_rule(user_data: rules.MonitoringRuleToggleRequest, db: Session = Depends(session.get_db)):
    """
    Toggles the is_active status of a monitoring rule.
    Updates the record in monitoring_rules if the user owns the rule.
    """

    # 1. Standard Security Verification
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    try:
        # Use a transaction block to save changes securely
        with db.begin():

            # 2. Raw SQL Update Query targeting the main rules table
            toggle_sql = text("""
                              UPDATE pgadmin_config
                              SET is_active = :is_active
                              WHERE id = :rule_id
                                AND user_id = :user_id;
                              """)

            result = db.execute(toggle_sql, {
                "is_active": user_data.is_active,
                "rule_id": user_data.rule_id,
                "user_id": user_data.user_id
            })

            # Check if the update affected any rows
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Rule not found or unauthorized access")

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during toggle update: {str(e)}")

    # 3. Clean success response
    return {
        "message": f"Monitoring Rule status updated successfully to {'active' if user_data.is_active else 'inactive'}",
        "rule_id": str(user_data.rule_id),
        "is_active": user_data.is_active
    }

@router.get("/rules/cameras")
def fetch_rule_and_available_cameras(
    username: str,
    jwt_token: str,
    user_id: str,
    rule_id: str,
    db: Session = Depends(session.get_db)
):
    """
    Fetches two lists for a rule:
    1. Cameras already linked to the monitoring rule.
    2. Cameras owned by the user but not linked to the monitoring rule.
    """

    # 1. Standard Security Verification
    token_verification = security.verify_token(jwt_token)

    if username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    # 2. Security Check: Verify the rule exists and belongs to this user
    check_rule_sql = text("""
        SELECT id FROM pgadmin_config WHERE id = :rule_id AND user_id = :user_id;
    """)
    rule_exists = db.execute(check_rule_sql, {"rule_id": rule_id, "user_id": user_id}).fetchone()

    if not rule_exists:
        raise HTTPException(status_code=404, detail="Monitoring Rule not found or unauthorized access")

    try:
        # 3. Fetch cameras that ARE linked to this specific rule
        linked_cameras_sql = text("""
            SELECT c.id, c.name
            FROM cameras c
            JOIN pgadmin_recover mrc ON c.id = mrc.camera_id
            WHERE mrc.rule_id = :rule_id;
        """)
        linked_result = db.execute(linked_cameras_sql, {"rule_id": rule_id})
        linked_cameras = linked_result.mappings().all()

        # 4. Fetch cameras that ARE NOT linked to this rule but belong to the user
        unlinked_cameras_sql = text("""
            SELECT c.id, c.name
            FROM cameras c
            WHERE c.user_id = :user_id
              AND c.id NOT IN (
                  SELECT camera_id 
                  FROM pgadmin_recover 
                  WHERE rule_id = :rule_id
              )
            ORDER BY c.name ASC;
        """)
        unlinked_result = db.execute(unlinked_cameras_sql, {"user_id": user_id, "rule_id": rule_id})
        unlinked_cameras = unlinked_result.mappings().all()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error while fetching cameras: {str(e)}")

    # 5. Return success response with both lists
    return {
        "message": "Rule cameras fetched successfully",
        "linked_cameras": linked_cameras,
        "unlinked_cameras": unlinked_cameras
    }


@router.post("/rules/update")
def update_monitoring_rule(user_data: rules.MonitoringRuleUpdateRequest, db: Session = Depends(session.get_db)):
    """
    Updates rule metadata and synchronizes the rule-camera links.
    Secures the operation by confirming user ownership of the rule.
    """

    # 1. Standard Security Verification
    token_verification = security.verify_token(user_data.jwt_token)

    if user_data.username != token_verification:
        raise HTTPException(status_code=400, detail="Verification Failed")

    try:
        # Use a transaction block to guarantee all modifications are treated as a unit
        with db.begin():

            # Step A: Update core rule metadata in the main table
            # Includes 'user_id' in WHERE to restrict updates to the rule owner
            update_rule_sql = text("""
                                   UPDATE pgadmin_config
                                   SET person_id = :person_id,
                                       rule_name = :rule_name,
                                       from_time = :from_time,
                                       to_time   = :to_time,
                                       is_active = :is_active
                                   WHERE id = :rule_id
                                     AND user_id = :user_id;
                                   """)

            result = db.execute(update_rule_sql, {
                "person_id": user_data.person_id,
                "rule_name": user_data.rule_name,
                "from_time": user_data.from_time,
                "to_time": user_data.to_time,
                "is_active": user_data.is_active,
                "rule_id": user_data.rule_id,
                "user_id": user_data.user_id
            })

            # Check if any rule was actually modified
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Rule not found or unauthorized access")

            # Step B: Delete existing camera associations for this rule
            delete_cameras_sql = text("""
                                      DELETE
                                      FROM pgadmin_recover
                                      WHERE rule_id = :rule_id;
                                      """)
            db.execute(delete_cameras_sql, {"rule_id": user_data.rule_id})

            # Step C: Re-insert new camera links into the junction table
            insert_cameras_sql = text("""
                                      INSERT INTO pgadmin_recover (rule_id, camera_id)
                                      VALUES (:rule_id, :camera_id);
                                      """)

            for cam_id in user_data.camera_ids:
                db.execute(insert_cameras_sql, {
                    "rule_id": user_data.rule_id,
                    "camera_id": cam_id
                })

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during update: {str(e)}")

    # 3. Clean success response matching existing format
    return {
        "message": "Monitoring Rule updated successfully",
        "rule_id": str(user_data.rule_id)
    }