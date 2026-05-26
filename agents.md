# Agent Security Guidelines

To ensure the safety, integrity, and security of the Losshound project, all AI agents and developers must strictly follow these instructions:

## Package Installation & Verification
* **Mandatory Pre-Installation Vetting:** Before installing any third-party package, dependency, binary, or external tool, it must be thoroughly vetted.
* **Vetting Criteria:**
  1. **Typosquatting Prevention:** Check the spelling of package names carefully to prevent accidental installation of malicious copycat packages on PyPI or other registries.
  2. **Reputation & Maintenance:** Review the library's source repository (e.g., GitHub stars, recent commits, open issues, and maintainer activity).
  3. **Dependency Footprint:** Ensure the package does not bring in hidden, bloated, or unsafe transitive dependencies.
  4. **Permission Requirements:** Avoid packages that ask for excessive system privileges unless absolutely necessary for Losshound's optimization/diagnostic tasks.
