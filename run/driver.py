#line 123 
import msgParser
import carState
import carControl
import keyboard
import csv
import os

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

    def drive(self, msg):
        self.state.setFromMsg(msg)

        rpm = self.state.getRpm()
        speedX = self.state.getSpeedX()
        gear = self.gear

        self.steer = 0.0
        self.accel = 0.0
        self.brake = 0.0

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
        max_speeds = [80, 120 , 160, 200, 250 , 300,330,360]
        max_speed = max_speeds[self.gear - 1] if 1 <= self.gear <= 7 else 50
        if forward_pressed:
            if speedX < max_speed:
                self.accel = 1.0
            else:
                self.accel = 0.2  # Maintain speed when at limit
        elif reverse_pressed:
            self.accel= 1.0
        else:
            self.accel= 0.0

        # --- Apply Control ---
        self.control.setGear(self.gear)
        self.control.setAccel(self.accel)
        self.control.setBrake(self.brake)
        self.control.setSteer(self.steer)

        # ! Opponent Data 
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
        
        # ! Track : 

        track_sensors = self.state.getTrack()
        track_position = self.state.getTrackPos()


    
        # --- Logging ---
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
            num_opponents , 
             *opponent_data,
            track_position,  # Current position on track
        ]
        
        # Add all 19 track sensor readings
        if track_sensors:
            log_data.extend(track_sensors)
        else:
            log_data.extend([200.0] * 19)  # Default value if sensors fail
            
        try:
            self.logger.writerow(log_data)
        except:
            pass

        for i, (angle, dist) in enumerate(active_opponents):
         print(f"  Opponent {i+1}: {dist:.1f}m at {angle}°")
        print(f"[SEND] steer={self.steer:.2f} accel={self.accel:.2f} brake={self.brake:.2f} gear={self.gear}")
        return self.control.toMsg()

    def onShutDown(self):
        self.logfile.close()

    def onRestart(self):
        pass
