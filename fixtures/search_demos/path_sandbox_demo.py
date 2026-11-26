"""Demo module: path sandbox concepts for CE-6 corpus."""

class PathSandboxError(ValueError):
    """Raised when a path escapes the workspace root."""
    pass

def resolve_safe(user_path: str, root: str) -> str:
    """Join root with user_path and reject escape via parent segments."""
    # demo implementation (not production)
    import os
    full = os.path.normpath(os.path.join(root, user_path))
    if not full.startswith(os.path.normpath(root)):
        raise PathSandboxError(user_path)
    return full

def demo_helper_1():
    return 1

def demo_helper_2():
    return 2

def demo_helper_3():
    return 3

def demo_helper_4():
    return 4

def demo_helper_5():
    return 5

def demo_helper_6():
    return 6

def demo_helper_7():
    return 7

def demo_helper_8():
    return 8

def demo_helper_9():
    return 9

def demo_helper_10():
    return 10

def demo_helper_11():
    return 11

def demo_helper_12():
    return 12

def demo_helper_13():
    return 13

def demo_helper_14():
    return 14

def demo_helper_15():
    return 15

def demo_helper_16():
    return 16

def demo_helper_17():
    return 17

def demo_helper_18():
    return 18

def demo_helper_19():
    return 19

def demo_helper_20():
    return 20

def demo_helper_21():
    return 21

def demo_helper_22():
    return 22

def demo_helper_23():
    return 23

def demo_helper_24():
    return 24

def demo_helper_25():
    return 25

def demo_helper_26():
    return 26

def demo_helper_27():
    return 27

def demo_helper_28():
    return 28

def demo_helper_29():
    return 29

def demo_helper_30():
    return 30

def demo_helper_31():
    return 31

def demo_helper_32():
    return 32

def demo_helper_33():
    return 33

def demo_helper_34():
    return 34

def demo_helper_35():
    return 35

def demo_helper_36():
    return 36

def demo_helper_37():
    return 37

def demo_helper_38():
    return 38

def demo_helper_39():
    return 39

def demo_helper_40():
    return 40

def demo_helper_41():
    return 41

def demo_helper_42():
    return 42

def demo_helper_43():
    return 43

def demo_helper_44():
    return 44

def demo_helper_45():
    return 45

def demo_helper_46():
    return 46

def demo_helper_47():
    return 47

def demo_helper_48():
    return 48

def demo_helper_49():
    return 49

def demo_helper_50():
    return 50

def demo_helper_51():
    return 51

def demo_helper_52():
    return 52

def demo_helper_53():
    return 53

def demo_helper_54():
    return 54

def demo_helper_55():
    return 55

def demo_helper_56():
    return 56

def demo_helper_57():
    return 57

def demo_helper_58():
    return 58

def demo_helper_59():
    return 59

def demo_helper_60():
    return 60

def demo_helper_61():
    return 61

def demo_helper_62():
    return 62

def demo_helper_63():
    return 63

def demo_helper_64():
    return 64

def demo_helper_65():
    return 65

def demo_helper_66():
    return 66

def demo_helper_67():
    return 67

def demo_helper_68():
    return 68

def demo_helper_69():
    return 69

def demo_helper_70():
    return 70

