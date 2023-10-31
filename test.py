zero = 400
nic = 100
strength = float(4)
replace = 30

while zero > 0:
    print(f"{round(strength, 2)}mg")
    zero = zero - replace
    strength = (nic-replace)*strength/nic