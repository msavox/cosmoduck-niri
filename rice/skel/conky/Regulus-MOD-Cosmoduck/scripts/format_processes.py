import sys

def format_process_data(data_lines):
    cpu_processes = []
    mem_processes = []

    # Skip header and get top 3 CPU processes
    for line in data_lines:
        parts = line.split()
        if len(parts) > 10: # Ensure it's a process line
            try:
                cpu_percent = float(parts[2])

                mem_percent = float(parts[3])
                cmd = parts[10]
                
                # Clean up command name (remove path)
                cmd_name_original = cmd.split('/')[-1]
                cmd_name_truncated = cmd_name_original[0:10]
                cmd_name = cmd_name_truncated.ljust(10)

                cpu_processes.append((cmd_name, cpu_percent))
                mem_processes.append((cmd_name, mem_percent))
            except ValueError:
                continue # Skip lines that don't parse

    # Sort and get top 3 for CPU
    cpu_processes.sort(key=lambda x: x[1], reverse=True)
    top_cpu = cpu_processes[:3]

    # Sort and get top 3 for RAM
    mem_processes.sort(key=lambda x: x[1], reverse=True)
    top_mem = mem_processes[:3]

    output = []
    output.append("TOP CPU PROCESSES") # Re-added title
    for name, percent in top_cpu:
        truncated_name = name[:15].ljust(13) # Truncate and pad
        output.append(f"      {truncated_name} {percent:.1f}%") # 6 spaces indentation

    output.append("      ") # Empty line for spacing, 6 spaces

    output.append("     TOP RAM PROCESSES") # Re-added title, 5 spaces
    
    for name, percent in top_mem:
        truncated_name = name[:15].ljust(13) # Truncate and pad
        output.append(f"      {truncated_name} {percent:.1f}%") # 6 spaces indentation

    return "\n".join(output)

if __name__ == "__main__":
    # Read all lines from stdin
    lines = sys.stdin.readlines()
    print(format_process_data(lines))