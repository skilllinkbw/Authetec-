import subprocess, os
os.chdir(r"C:\Users\DELL\Documents\GitHub\Authetec-")
subprocess.run(["git", "checkout", "--", "Authetec and compliance.html"])
subprocess.run(["git", "checkout", "--", "Authetec full code.html"])
print("Files restored")
