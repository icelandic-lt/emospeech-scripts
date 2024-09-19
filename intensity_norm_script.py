import argparse
import numpy as np
import re
import matplotlib.pyplot as plt
from scipy.stats import truncnorm


def create_normal_distribution(n, mean, std_dev, min_val, max_val):
    if n <= 0:
        raise ValueError("N must be greater than 0.")
    if std_dev <= 0:
        raise ValueError("Standard deviation must be greater than 0.")
    if min_val >= max_val:
        raise ValueError("Minimum value must be less than maximum value.")

    # Calculate the standardized boundaries
    a, b = (min_val - mean) / std_dev, (max_val - mean) / std_dev

    # Generate the truncated normal distribution
    distribution = truncnorm.rvs(a, b, loc=mean, scale=std_dev, size=n)

    rounded_distribution = np.round(distribution).astype(int)

    return ' '.join(map(str, rounded_distribution))


def plot_distribution(distribution, min_val, max_val):
    plt.figure(figsize=(12, 6))

    # Histogram of the distribution
    plt.subplot(1, 2, 1)
    plt.hist(distribution, bins=range(min_val, max_val + 2), align='left', rwidth=0.8, density=True)
    plt.title('Distribution of Generated Numbers')
    plt.xlabel('Value')
    plt.ylabel('Relative Frequency')
    plt.xticks(range(min_val, max_val + 1))
    plt.grid(axis='y', alpha=0.75)

    # Theoretical normal distribution for comparison
    x = np.linspace(min_val, max_val, 100)
    plt.plot(x, truncnorm.pdf(x, a=(min_val-np.mean(distribution))/np.std(distribution),
                              b=(max_val-np.mean(distribution))/np.std(distribution),
                              loc=np.mean(distribution), scale=np.std(distribution)),
             'r-', lw=2, label='Theoretical Distribution')
    plt.legend()

    # Scatter plot of actual values
    plt.subplot(1, 2, 2)
    plt.scatter(range(len(distribution)), distribution, alpha=0.5)
    plt.title('Scatter Plot of Values')
    plt.xlabel('Index')
    plt.ylabel('Value')
    plt.yticks(range(min_val, max_val + 1))
    plt.grid(True)

    plt.tight_layout()
    plt.show()


def process_script(input_file, output_file, distribution):
    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        for i, line in enumerate(infile):
            if i < len(distribution):
                value = distribution[i]
                before_colon, after_colon = line.split(':', 1)
                parts = before_colon.split()
                parts[-1] = f'"{str(value)}'
                modified_line = f'{" ".join(parts)}:{after_colon}'
                outfile.write(modified_line)
            else:
                outfile.write(line)


def analyze_script(input_file):
    values = []
    pattern = r'(\d+):'

    with open(input_file, 'r') as infile:
        for line in infile:
            match = re.search(pattern, line)
            if match:
                values.append(int(match.group(1)))

    if values:
        mean = np.mean(values)
        std_dev = np.std(values)
        min_val = min(values)
        max_val = max(values)
        return mean, std_dev, min_val, max_val
    else:
        return None


def extract_values_from_script(input_file):
    values = []
    pattern = r'(\d+):'

    with open(input_file, 'r') as infile:
        for line in infile:
            match = re.search(pattern, line)
            if match:
                values.append(int(match.group(1)))

    return values


def main():
    parser = argparse.ArgumentParser(description='Creates a normal distribution and processes a script.')
    parser.add_argument('--N', type=int, help='Number of numbers to generate')
    parser.add_argument('--mean', type=float, help='Mean of the normal distribution')
    parser.add_argument('--std_dev', type=float, help='Standard deviation of the normal distribution')
    parser.add_argument('--min_val', type=int, help='Smallest allowed number in the distribution')
    parser.add_argument('--max_val', type=int, help='Largest allowed number in the distribution')
    parser.add_argument('--plot', action='store_true', help='Shows a graphical representation of the distribution')
    parser.add_argument('--script', type=str, help='Input script file')
    parser.add_argument('--output', '-o', type=str, help='Output script file')

    args = parser.parse_args()

    # Analyse mode
    if args.script and not any([args.mean, args.std_dev, args.min_val, args.max_val, args.output]):
        result = analyze_script(args.script)
        if result:
            mean, std_dev, min_val, max_val = result
            print(f"Analysis results:")
            print(f"Mean: {mean:.2f}")
            print(f"Standard deviation: {std_dev:.2f}")
            print(f"Minimum value: {min_val}")
            print(f"Maximum value: {max_val}")

            if args.plot:
                values = extract_values_from_script(args.script)
                plot_distribution(values, min_val, max_val)
        else:
            print("The script does not contain normal distribution normalized values.")
        return

    # Processing mode
    if args.script and args.output:
        if not all([args.mean, args.std_dev, args.min_val, args.max_val]):
            print("Error: For processing a script, you must provide --mean, --std_dev, --min_val, and --max_val.")
            return

        with open(args.script, 'r') as f:
            num_lines = sum(1 for _ in f)

        if args.N is None:
            args.N = num_lines
        elif args.N > num_lines:
            print(f"Warning: N ({args.N}) is greater than the number of lines ({num_lines}). Only {num_lines} lines will be processed.")
            args.N = num_lines

        try:
            result = create_normal_distribution(args.N, args.mean, args.std_dev, args.min_val, args.max_val)
            distribution = list(map(int, result.split()))
            process_script(args.script, args.output, distribution)
            print(f"Processed script has been saved in {args.output}.")

            if args.plot:
                plot_distribution(distribution, args.min_val, args.max_val)
        except ValueError as e:
            print(f"Error: {str(e)}")

    # Distribution generation mode
    elif all([args.N, args.mean, args.std_dev, args.min_val, args.max_val]):
        try:
            result = create_normal_distribution(args.N, args.mean, args.std_dev, args.min_val, args.max_val)
            print(result)

            if args.plot:
                distribution = list(map(int, result.split()))
                plot_distribution(distribution, args.min_val, args.max_val)
        except ValueError as e:
            print(f"Error: {str(e)}")

    else:
        print("Error: Invalid combination of arguments.")
        print("To analyze a script, use: --script")
        print("To process a script, use: --script, --output, --mean, --std_dev, --min_val, --max_val")
        print("To generate a distribution, use: --N, --mean, --std_dev, --min_val, --max_val")
        print("Add --plot to any mode to show a graphical representation.")

if __name__ == '__main__':
    main()
