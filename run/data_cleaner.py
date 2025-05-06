#The purpose of this is to compile all "input readings" into 1 singular field called target_action

import pandas as pd

df = pd.read_csv("driving_data.csv")

target_actions = []

# Process row-by-row to access previous gear
for i in range(len(df)):
    if i > 0 and df.loc[i, "gear"] > df.loc[i-1, "gear"]:
        target_actions.append("gear_up")
    elif i > 0 and df.loc[i, "gear"] < df.loc[i-1, "gear"]:
        target_actions.append("gear_down")
    elif df.loc[i, "brake_input"] != 0:
        target_actions.append("brake")
    elif df.loc[i, "steer_input"] < 0:
        target_actions.append("right")
    elif df.loc[i,"steer_input"] > 0:
        target_actions.append("left")
    elif df.loc[i, "accel_input"] != 0:
        target_actions.append("throttle")
    else:
        target_actions.append("no_action")

# Add new column
df["target_action"] = target_actions

df = df.drop(columns=['steer_input','accel_input','brake_input'])
df.head()
df = df[df["target_action"] != "no_action"]
df.head()
df.to_csv("cleaned_data.csv", index=False)
