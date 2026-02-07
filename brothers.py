BROTHERS = {
    "jerry": {
        "host": "cluster",
        "working_dir": None,
        "command": "ssh -t cluster \"bash -lc claude\"",
        "description": "Brother Jerry — GPU jobs on the cluster",
    },
    "oppy": {
        "host": "masuda",
        "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
        "command": "ssh -t masuda \"bash -lc 'cd ~/projects/mol_diffusion/OMTRA_oppy && claude'\"",
        "description": "Brother Oppy — The architect on masuda",
    },
}
