import msgParser
import carState
import carControl
import keyboard
import csv
import os
import numpy as np
import joblib
import time

class Driver(object):
    def __init__(self, stage):
        self.stage = stage
        self.parser = msgParser.MsgParser()
        self.state = carState.CarState()
        self.control = carControl.CarControl()

        self.gear = 1
        self.prev_speedX = 0.0
        self.accel = 0.0
        self.brake = 0.0
        self.steer = 0.0

        self.last_gear_up = False
        self.last_gear_down = False
        self.was_reversing = False

        self.last_shift_time = 0
        
        # Load the trained model and scaler
        try:
            self.model = joblib.load("../Dataset/model.pkl")
            self.scaler = joblib.load("../Dataset/scaler.pkl")
            self.autonomous_mode = True
            print("Autonomous driving mode enabled - model loaded successfully!")
        except FileNotFoundError:
            self.autonomous_mode = False
            print("Model files not found. Falling back to manual control.")
            
        # Action mapping (reverse of what's in train_model.ipynb)
        self.action_mapping = {
            0: "left",
            1: "right",
            2: "gear_up",
            3: "gear_down",
            4: "brake",
            5: "throttle"
        }
        
        file_exists = os.path.isfile("driving_data.csv")
        self.logfile = open("driving_data.csv", "a", newline="")
        self.logger = csv.writer(self.logfile)
        
        # Only write headers if file is new
        if not file_exists:
            self.logger.writerow([
                "speedX", "speedY", "speedZ", "angle", "trackPos", "rpm",
                "gear", "steer_input", "accel_input", "brake_input",
                "num_opponents",
                *[f"opponent_{i}_angle" for i in range(10)],
                *[f"opponent_{i}_distance" for i in range(10)],
                "track_pos",
                *[f"track_{i}" for i in range(19)]
            ])

    def init(self):
        angles = [0] * 19
        for i in range(5):
            angles[i] = -90 + i * 15
            angles[18 - i] = 90 - i * 15
        for i in range(5, 9):
            angles[i] = -20 + (i - 5) * 5
            angles[18 - i] = 20 - (i - 5) * 5
        return self.parser.stringify({'init': angles})

    def predict_action(self):
        """Use the trained model to predict the next action"""
        # Get current state
        features = self.prepare_model_input()
        
        # Scale the features
        scaled_features = self.scaler.transform([features])
        
        # Predict action
        action_code = self.model.predict(scaled_features)[0]
        
        # Map the action code to an actual action
        action = self.action_mapping.get(action_code, "throttle")
        
        return action

    def prepare_model_input(self):
        """Prepare the input features for the model in the same order as training data"""
        speedX = self.state.getSpeedX()
        speedY = self.state.getSpeedY()
        speedZ = self.state.getSpeedZ()
        angle = self.state.getAngle()
        trackPos = self.state.getTrackPos()
        rpm = self.state.getRpm()
        gear = self.gear
        
        # Opponent data
        opponents = self.state.getOpponents()
        active_opponents = []
        
        if opponents:
            # Scan all angles for opponents
            for angle_idx in range(0, 360, 10):
                idx = angle_idx // 10
                distance = opponents[idx]
                if distance < 200.0:  # Opponent detected
                    active_opponents.append((angle_idx, distance))
            
            # Sort by distance to prioritize closest opponents
            active_opponents.sort(key=lambda x: x[1])
        
        # Prepare opponent data
        num_opponents = len(active_opponents)
        opponent_angles = []
        opponent_distances = []
        
        # Add angles and distances, pad with defaults if needed
        for i in range(10):  # Support up to 10 opponents
            if i < num_opponents:
                opponent_angles.append(active_opponents[i][0])
                opponent_distances.append(active_opponents[i][1])
            else:
                opponent_angles.append(0)
                opponent_distances.append(200.0)  # Default values for empty slots
        
        # Track data
        track_sensors = self.state.getTrack()
        track_position = self.state.getTrackPos()
        
        if not track_sensors:
            track_sensors = [200.0] * 19  # Default value if sensors fail
            
        # Assemble input features in the same order as training data
        features = [
            speedX, speedY, speedZ, angle, trackPos, rpm, gear, num_opponents,
            *opponent_angles, *opponent_distances, track_position, *track_sensors
        ]
        
        return features

    def drive(self, msg):
        self.state.setFromMsg(msg)

        rpm = self.state.getRpm()
        speedX = self.state.getSpeedX()
        gear = self.gear

        # Default values
        self.steer = 0.0
        self.accel = 0.0
        self.brake = 0.0
        
        # --- Autonomous or Manual Mode ---
        if self.autonomous_mode and not keyboard.is_pressed('m'):
            # Get the predicted action
            action = self.predict_action()
            
            # Apply the predicted action
            if action == "left":
                self.steer = 0.5
            elif action == "right":
                self.steer = -0.5
            elif action == "gear_up":
                self.gear = min(self.gear + 1, 7)
            elif action == "gear_down":
                self.gear = max(self.gear - 1, 1)
            elif action == "brake":
                self.brake = 1.0
            elif action == "throttle":
                self.accel = 1.0
                
            # Basic safety checks
            if speedX < 0 and self.gear > 0:
                # We're moving backwards but in a forward gear
                self.gear = -1
            elif speedX > 0 and self.gear < 0:
                # We're moving forwards but in reverse gear
                self.gear = 1
                
            current_time = time.time()  # Get current time
            
            # Only process auto-shifting if not manually changing gear and cooldown has expired
            if action != "gear_up" and action != "gear_down" and current_time - self.last_shift_time > 0.5:  # 0.5 second cooldown
                if rpm > 8000 and self.gear < 7:
                    self.gear += 1
                    self.last_shift_time = current_time  # Update last shift time
                elif rpm < 3000 and self.gear > 1:
                    self.gear -= 1
                    self.last_shift_time = current_time  # Update last shift time
            
            print(f"Autonomous mode: {action}")
        else:
            # --- Manual Control mode ---
            print("Manual control mode")
            
            # --- Steering ---
            if keyboard.is_pressed('a'):
                self.steer = 0.8
            elif keyboard.is_pressed('d'):
                self.steer = -0.8

            # --- Collision Detection ---
            if self.prev_speedX - speedX > 50:  
                print("Collision detected! Resetting gear to 1.")
                self.gear = 1

            self.prev_speedX = speedX  # Update previous speed

            # --- Reverse / Forward Management ---
            reversing = False
            forward_pressed = keyboard.is_pressed('w')
            reverse_pressed = keyboard.is_pressed('s')

            if reverse_pressed and speedX < 1:
                self.accel = 0.5
                self.gear = -1
                reversing = True
            elif forward_pressed:
                self.accel = 1.0
                if self.gear < 1:
                    self.gear = 1  # Switch to forward gear after reversing
                reversing = False
            elif reverse_pressed:
                self.brake = 1.0
            else:
                self.accel = 0.0

            # --- Manual Gear Override ---
            manual_override = False
            if keyboard.is_pressed('up'):  # Shift Up
                if not self.last_gear_up:
                    self.gear = min(self.gear + 1, 7)
                    self.last_gear_up = True
                    manual_override = True
            else:
                self.last_gear_up = False

            if keyboard.is_pressed('down'):  # Shift Down
                if not self.last_gear_down:
                    self.gear = max(self.gear - 1, 1)
                    self.last_gear_down = True
                    manual_override = True
            else:
                self.last_gear_down = False

            # --- Adjust Speed Based on Gear ---
            max_speeds = [80, 120, 160, 200, 250, 300, 330, 360]
            max_speed = max_speeds[self.gear - 1] if 1 <= self.gear <= 7 else 50
            if forward_pressed:
                if speedX < max_speed:
                    self.accel = 1.0
                else:
                    self.accel = 0.2  # Maintain speed when at limit
            elif reverse_pressed:
                self.accel = 1.0
            else:
                self.accel = 0.0

        # --- Apply Control ---
        # Make sure the gear value is valid before applying
        if self.gear < -1:
            self.gear = -1
        elif self.gear == 0:
            self.gear = 1  # Skip neutral gear
        elif self.gear > 7:
            self.gear = 7
            
        self.control.setGear(self.gear)
        self.control.setAccel(self.accel)
        self.control.setBrake(self.brake)
        self.control.setSteer(self.steer)
        
        # Debug output for gear
        print(f"Current gear: {self.gear} | Control gear: {self.control.getGear()}")

        # Log all the data for further training
        #self.log_data()
        
        print(f"[SEND] steer={self.steer:.2f} accel={self.accel:.2f} brake={self.brake:.2f} gear={self.gear}")
        return self.control.toMsg()

    def log_data(self):
        """Log driving data for future training"""
        # Get opponent data
        opponents = self.state.getOpponents()
        active_opponents = []
        
        if opponents:
            # Scan all angles for opponents
            for angle in range(0, 360, 10):
                idx = angle // 10
                distance = opponents[idx]
                if distance < 200.0:  # Opponent detected
                    active_opponents.append((angle, distance))
            
            # Sort by distance to prioritize closest opponents
            active_opponents.sort(key=lambda x: x[1])
        
        # Prepare opponent data for logging
        num_opponents = len(active_opponents)
        opponent_data = []
        
        # Add angles and distances, pad with defaults if needed
        for i in range(10):  # Support up to 10 opponents
            if i < num_opponents:
                opponent_data.extend([active_opponents[i][0], active_opponents[i][1]])
            else:
                opponent_data.extend([0, 200.0])  # Default values for empty slots
        
        # Track data
        track_sensors = self.state.getTrack()
        track_position = self.state.getTrackPos()
        
        # Logging data
        log_data = [
            self.state.getSpeedX(),
            self.state.getSpeedY(),
            self.state.getSpeedZ(),
            self.state.getAngle(),
            self.state.getTrackPos(),
            self.state.getRpm(),
            self.gear,
            self.steer,
            self.accel,
            self.brake,
            num_opponents,
            *opponent_data,
            track_position,
        ]
        
        # Add all 19 track sensor readings
        if track_sensors:
            log_data.extend(track_sensors)
        else:
            log_data.extend([200.0] * 19)  # Default value if sensors fail
            
        try:
            self.logger.writerow(log_data)
        except Exception as e:
            print(f"Error logging data: {e}")

    def onShutDown(self):
        self.logfile.close()

    def onRestart(self):
        pass